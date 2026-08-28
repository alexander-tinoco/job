# syntax=docker/dockerfile:1

# Tesseract is a system binary, not a Python package. Without it a scanned
# résumé is still accepted and still flagged, but never OCR'd (README § OCR).
FROM python:3.14-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY pyproject.toml ./
# Dependencies resolve from pyproject alone, so this layer is cached until the
# dependency list itself changes.
RUN pip install --no-cache-dir .

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

# Runs as a non-root user: uploaded résumés are untrusted input and PyMuPDF
# parses them in this process.
RUN useradd --system --create-home --uid 10001 screening \
 && mkdir -p /srv/uploads \
 && chown -R screening:screening /srv
USER screening

EXPOSE 8000

# Migrations run at start, not by hand after each deploy. Idempotent: on an
# up-to-date database `upgrade head` is a no-op.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
