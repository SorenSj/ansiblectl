"""Unit tests for versioned command envelopes."""

from typing import Any

import pytest

from ansiblectl.domain.context import CommandContext
from ansiblectl.domain.envelopes import (
    ENVELOPE_SCHEMA_VERSION,
    ErrorEnvelope,
    StructuredError,
    SuccessEnvelope,
)
from ansiblectl.domain.errors import ConflictError, ValidationError
from ansiblectl.domain.results import CommandResult, CommandWarning

_OPERATION_ID = "00000000Z80000000000000000"


def _context() -> CommandContext:
    return CommandContext(_OPERATION_ID, "repository create", False, "json", False)


def test_success_envelope_contains_the_complete_versioned_schema() -> None:
    warning = CommandWarning(
        "DEFAULT_BRANCH_ASSUMED",
        "The default branch was not explicit.",
        {"branch": "main"},
    )
    result = CommandResult(
        data={"name": "automation"},
        message="Repository created.",
        changed=True,
        warnings=(warning,),
        metadata={"adapter": "git"},
    )

    envelope = SuccessEnvelope.from_result(_context(), result)

    assert envelope.to_payload() == {
        "schema_version": "1",
        "status": "success",
        "operation_id": _OPERATION_ID,
        "command": "repository create",
        "changed": True,
        "message": "Repository created.",
        "data": {"name": "automation"},
        "warnings": [
            {
                "code": "DEFAULT_BRANCH_ASSUMED",
                "message": "The default branch was not explicit.",
                "context": {"branch": "main"},
            }
        ],
        "metadata": {"adapter": "git"},
    }


def test_error_envelope_excludes_cause_and_preserves_safe_details() -> None:
    cause = OSError("private adapter detail")
    error = ConflictError(
        "Repository already exists.",
        detail="The destination is not empty.",
        hint="Choose another destination.",
        context={"repository": "automation"},
        cause=cause,
    )

    envelope = ErrorEnvelope.from_error(
        _context(),
        error,
        warnings=(CommandWarning("NOTICE", "No files were changed."),),
        metadata={"attempt": 1},
    )

    assert envelope.to_payload() == {
        "schema_version": "1",
        "status": "error",
        "operation_id": _OPERATION_ID,
        "command": "repository create",
        "changed": False,
        "error": {
            "code": "CONFLICT",
            "category": "conflict",
            "message": "Repository already exists.",
            "detail": "The destination is not empty.",
            "hint": "Choose another destination.",
            "context": {"repository": "automation"},
        },
        "warnings": [{"code": "NOTICE", "message": "No files were changed.", "context": {}}],
        "metadata": {"attempt": 1},
    }
    assert "cause" not in envelope.error.to_payload()


def test_envelope_defaults_remain_explicit_in_machine_payloads() -> None:
    success = SuccessEnvelope.from_result(_context(), CommandResult[None]())
    failure = ErrorEnvelope.from_error(_context(), ConflictError("Conflict."))

    assert success.to_payload()["message"] is None
    assert success.to_payload()["data"] is None
    assert success.to_payload()["warnings"] == []
    assert failure.to_payload()["warnings"] == []
    assert failure.to_payload()["metadata"] == {}
    assert ENVELOPE_SCHEMA_VERSION == "1"


def test_structured_error_copies_context_from_error() -> None:
    source = {"resource": "original"}
    error = ConflictError("Conflict.", context=source)
    structured = StructuredError.from_error(error)

    source["resource"] = "changed"

    assert structured.context == {"resource": "original"}


def test_envelope_metadata_is_defensively_immutable() -> None:
    metadata = {"adapter": "git"}
    envelope = SuccessEnvelope[None](
        _OPERATION_ID,
        "repository create",
        False,
        metadata=metadata,
    )

    metadata["adapter"] = "changed"

    assert envelope.metadata == {"adapter": "git"}
    with pytest.raises(TypeError):
        envelope.metadata["adapter"] = "changed"


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"schema_version": "2"}, "schema version"),
        ({"status": "error"}, "status must match"),
        ({"changed": 1}, "changed flag must be a boolean"),
        ({"warnings": []}, "warnings must be a tuple"),
        ({"metadata": {1: "value"}}, "metadata must be a string-keyed"),
    ],
)
def test_success_envelope_rejects_schema_invalid_runtime_values(
    arguments: dict[str, Any], message: str
) -> None:
    values: dict[str, Any] = {
        "operation_id": _OPERATION_ID,
        "command": "repository create",
        "changed": False,
    }
    values.update(arguments)

    with pytest.raises(ValidationError, match=message):
        SuccessEnvelope[None](**values)


def test_error_envelope_requires_false_changed_flag() -> None:
    error = StructuredError("CONFLICT", "conflict", "Conflict.")

    with pytest.raises(ValidationError, match="changed flag must be false"):
        ErrorEnvelope(_OPERATION_ID, "repository create", error, changed=True)


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"code": "invalid"}, "uppercase identifier"),
        ({"category": "INVALID"}, "lowercase identifier"),
        ({"message": " "}, "message must be non-empty"),
        ({"context": []}, "string-keyed mapping"),
    ],
)
def test_structured_error_rejects_schema_invalid_runtime_values(
    arguments: dict[str, Any], message: str
) -> None:
    values: dict[str, Any] = {
        "code": "CONFLICT",
        "category": "conflict",
        "message": "Conflict.",
    }
    values.update(arguments)

    with pytest.raises(ValidationError, match=message):
        StructuredError(**values)
