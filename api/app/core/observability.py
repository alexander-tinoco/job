"""Logs, traces and metrics.

The problem this exists to solve: until now, if a batch stalled overnight there
was no way to find out why without opening the database. Twelve `logger` calls
across eight of seventy-five modules, no request context, no metrics, no traces.

Three pieces, in the order they earn their keep:

1. **A correlation id on every log line.** It is the OpenTelemetry trace id, not
   a separate identifier, so a log line and its trace are the same thing looked
   at from two sides. Without a trace it falls back to a random id, which is
   still enough to gather one request's lines together.
2. **Traces**, always recorded and exported only when an OTLP endpoint is set.
   An unconfigured deployment drops them for the cost of building a span, which
   keeps a $10/month box a $10/month box.
3. **Metrics**, the numbers you want *before* you know which trace to look for:
   how deep the queue is, how long batches take, what has been spent.

No personal data reaches any of them. The rule is the same as everywhere else in
this project: log the `application_id`, never the candidate.
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
import uuid
from contextvars import ContextVar
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

from app.core.config import get_settings

# One registry rather than the global default: two test runs in one process
# would otherwise collide on duplicate metric names.
REGISTRY = CollectorRegistry()

requests_total = Counter(
    "verbatim_requests_total",
    "HTTP requests served.",
    ["method", "route", "status"],
    registry=REGISTRY,
)
request_seconds = Histogram(
    "verbatim_request_seconds",
    "Time to serve an HTTP request.",
    ["method", "route"],
    registry=REGISTRY,
)
evaluations_total = Counter(
    "verbatim_evaluations_total",
    "Candidate evaluations, by how they ended.",
    ["outcome"],
    registry=REGISTRY,
)
tokens_total = Counter(
    "verbatim_tokens_total",
    "Model tokens consumed. The number a bill is made of.",
    ["direction"],
    registry=REGISTRY,
)
batches_total = Counter(
    "verbatim_batches_total", "Batches submitted.", ["outcome"], registry=REGISTRY
)
queue_depth = Gauge(
    "verbatim_queue_depth",
    "Rows waiting, by state. Sampled when readiness is checked.",
    ["state"],
    registry=REGISTRY,
)
queue_oldest_seconds = Gauge(
    "verbatim_queue_oldest_pending_seconds",
    "Age of the oldest row still waiting. The number that says a batch stalled.",
    registry=REGISTRY,
)


# --- The canonical log line ---------------------------------------------
#
# One wide line per request instead of a scatter of narrow ones. The difference
# in practice: answering "what happened to that application?" is a single
# search returning a single line that already holds every fact, rather than
# stitching together an access log, a handler's message and a stack trace by
# timestamp and hoping nothing interleaved.
#
# Handlers add to it with `note()`, so a fact is recorded where it is known
# rather than plumbed through return values.

_canonical: ContextVar[dict[str, Any]] = ContextVar("canonical")

request_logger = logging.getLogger("app.request")


def begin_request() -> None:
    _canonical.set({})


def note(**fields: Any) -> None:
    """Add facts to the line this request will emit when it finishes.

    Identifiers only, never candidate content: `application_id`, `batch_id`, a
    count. The rule is the one that governs every log in this project — the
    panel can look a person up from an id; a log store should not be able to.
    """
    # Outside a request (a worker tick, a CLI run) there is no line to add to,
    # and losing the note is better than raising into the caller.
    with contextlib.suppress(LookupError):
        _canonical.get().update(fields)


def emit_request(method: str, route: str, status: int, seconds: float) -> None:
    fields: dict[str, Any] = {}
    with contextlib.suppress(LookupError):
        fields = _canonical.get()
    request_logger.info(
        "request",
        extra={
            "method": method,
            "route": route,
            "status": status,
            "duration_ms": round(seconds * 1000, 2),
            **fields,
        },
    )


def correlation_id() -> str:
    """The current trace id, or a fresh one when nothing is being traced."""
    span = trace.get_current_span()
    context = span.get_span_context()
    if context.is_valid:
        return format(context.trace_id, "032x")
    return uuid.uuid4().hex


class CorrelationFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id()
        return True


# Everything a LogRecord carries by default. Anything else was passed by the
# caller through `extra=` and is theirs to have emitted.
_STANDARD = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "asctime",
    "message",
    "taskName",
    "correlation_id",
    # Uvicorn attaches an ANSI-coloured copy of its own message. Useful in a
    # terminal, noise in a log store.
    "color_message",
}


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with the fields a search needs first."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", ""),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


# Uvicorn installs its own handlers on these and sets `propagate = False`, so
# replacing the root handler leaves the server's own output untouched — which is
# most of what a deployment actually prints. They have to be handed back.
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


def configure_logging() -> None:
    settings = get_settings()
    handler = logging.StreamHandler()
    handler.addFilter(CorrelationFilter())
    handler.setFormatter(
        JsonFormatter()
        if settings.log_json
        else logging.Formatter(
            "%(asctime)s %(levelname)-7s [%(correlation_id)s] %(name)s: %(message)s"
        )
    )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level.upper())

    for name in _UVICORN_LOGGERS:
        server = logging.getLogger(name)
        server.handlers = []
        server.propagate = True

    # Silenced, not reformatted. Its line carries strictly less than the
    # canonical one and would double every request in the log store; the point
    # of a canonical line is that there is exactly one per request.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


_tracing: TracerProvider | None = None


def configure_tracing() -> TracerProvider:
    """Record spans always; ship them only when there is somewhere to ship to.

    Idempotent: the provider is global, so configuring twice would stack
    exporters and log a warning on every reload.
    """
    global _tracing
    if _tracing is not None:
        return _tracing

    settings = get_settings()
    provider = TracerProvider(
        resource=Resource.create(
            {"service.name": settings.service_name, "deployment.environment": settings.environment}
        )
    )
    if settings.otel_endpoint:
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_endpoint))
        )
    trace.set_tracer_provider(provider)
    _tracing = provider
    return provider


class Timer:
    """Wall-clock for a block, in seconds."""

    def __enter__(self) -> Timer:
        self._started = time.perf_counter()
        return self

    def __exit__(self, *_: object) -> None:
        self.seconds = time.perf_counter() - self._started
