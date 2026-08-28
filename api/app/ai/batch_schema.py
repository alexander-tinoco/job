"""Build the strict JSON Schema block the Batch API needs.

`responses.parse(text_format=Model)` does not exist on the batch path, so the
request body has to carry a raw schema. Pydantic's `model_json_schema()` is
almost right but omits `additionalProperties: false`, and strict mode refuses a
schema without it — verified against the API, which answers:

    Invalid schema for response_format 'evaluation':
    In context=(), 'additionalProperties' is required to be supplied and to be false

`$defs` and `$ref` are fine and are left alone; an earlier note in this project
claimed strict mode rejected them, which was wrong.

This matters beyond plumbing. Without `strict: true` the batch path would lose
layer 2 of the anti-injection design (plan §6) in exactly the place production
runs, while the synchronous path kept it.
"""

from __future__ import annotations

import copy
from typing import Any

from app.ai.schema import EvaluationOutput

SCHEMA_NAME = "evaluation"


def harden(node: Any) -> Any:
    """Recursively make every object closed and every property required.

    Strict mode's two demands: no properties beyond those declared, and no
    optional ones. Applied to `$defs` entries as well, since a nested object is
    checked with the same rules as the root.
    """
    if isinstance(node, dict):
        if node.get("type") == "object":
            node["additionalProperties"] = False
            if "properties" in node:
                node["required"] = list(node["properties"])
        for value in node.values():
            harden(value)
    elif isinstance(node, list):
        for value in node:
            harden(value)
    return node


def evaluation_schema() -> dict[str, Any]:
    """The hardened schema for `EvaluationOutput`."""
    schema: dict[str, Any] = copy.deepcopy(EvaluationOutput.model_json_schema())
    hardened: dict[str, Any] = harden(schema)
    return hardened


def text_format() -> dict[str, Any]:
    """The `text` block of a batch request body."""
    return {
        "format": {
            "type": "json_schema",
            "name": SCHEMA_NAME,
            "strict": True,
            "schema": evaluation_schema(),
        }
    }
