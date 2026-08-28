"""Layer 2 must survive the batch path (plan §6).

`responses.parse(text_format=Model)` does not exist for batches, so the schema
travels raw and it is easy to ship one strict mode silently rejects — which
would leave production without the guarantee the synchronous path has.
"""

from typing import Any

from app.ai.batch_schema import evaluation_schema, harden, text_format
from app.ai.schema import EvaluationOutput


def _objects(node: Any, path: str = "root") -> list[tuple[str, dict[str, Any]]]:
    found: list[tuple[str, dict[str, Any]]] = []
    if isinstance(node, dict):
        if node.get("type") == "object":
            found.append((path, node))
        for key, value in node.items():
            found.extend(_objects(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(_objects(value, f"{path}[{index}]"))
    return found


def test_the_raw_pydantic_schema_would_be_rejected() -> None:
    """The exact gap that makes hardening necessary, pinned so it stays visible.

    The API answers: "In context=(), 'additionalProperties' is required to be
    supplied and to be false".
    """
    raw = EvaluationOutput.model_json_schema()

    assert "additionalProperties" not in raw


def test_every_object_is_closed_and_fully_required() -> None:
    for path, node in _objects(evaluation_schema()):
        assert node.get("additionalProperties") is False, f"{path} is open"
        assert set(node.get("required", [])) == set(node.get("properties", {})), (
            f"{path} has optional properties"
        )


def test_nested_definitions_are_hardened_too() -> None:
    """A nested object is checked with the same rules as the root."""
    schema = evaluation_schema()

    assert "$defs" in schema
    nested = schema["$defs"]["CriterionAssessment"]
    assert nested["additionalProperties"] is False
    assert set(nested["required"]) == set(nested["properties"])


def test_refs_are_left_alone() -> None:
    """Strict mode accepts $ref. An earlier note in this project said otherwise."""
    schema = evaluation_schema()

    assert schema["properties"]["criteria"]["items"]["$ref"] == "#/$defs/CriterionAssessment"


def test_the_request_block_declares_strict() -> None:
    block = text_format()["format"]

    assert block["strict"] is True
    assert block["type"] == "json_schema"
    assert block["name"] == "evaluation"


def test_hardening_does_not_mutate_the_model_schema() -> None:
    """A shared mutable schema would leak hardening into the synchronous path."""
    before = EvaluationOutput.model_json_schema()
    evaluation_schema()
    after = EvaluationOutput.model_json_schema()

    assert before == after


def test_harden_is_idempotent() -> None:
    once = evaluation_schema()
    twice = harden(evaluation_schema())

    assert once == twice
