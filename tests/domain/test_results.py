"""Unit tests for structured command-result models."""

from dataclasses import FrozenInstanceError

import pytest

from ansiblectl.domain.errors import ValidationError
from ansiblectl.domain.results import CommandResult, CommandWarning


def test_command_result_defaults_describe_an_unchanged_empty_success() -> None:
    result = CommandResult[dict[str, object]]()

    assert result.data is None
    assert result.message is None
    assert result.changed is False
    assert result.warnings == ()
    assert result.metadata == {}


def test_command_result_carries_typed_data_warnings_and_metadata() -> None:
    warning = CommandWarning(
        code="REPOSITORY_DIRTY",
        message="The repository contains uncommitted changes.",
        context={"repository": "automation"},
    )
    result = CommandResult(
        data={"name": "automation", "path": "/srv/automation"},
        message="Repository inspected.",
        changed=False,
        warnings=(warning,),
        metadata={"revision": "main"},
    )

    assert result.data == {"name": "automation", "path": "/srv/automation"}
    assert result.message == "Repository inspected."
    assert result.warnings == (warning,)
    assert result.metadata == {"revision": "main"}


def test_default_mappings_are_not_shared_between_instances() -> None:
    first_result = CommandResult[None]()
    second_result = CommandResult[None]()
    first_warning = CommandWarning("FIRST", "First warning.")
    second_warning = CommandWarning("SECOND", "Second warning.")

    assert first_result.metadata is not second_result.metadata
    assert first_warning.context is not second_warning.context


def test_result_and_warning_fields_cannot_be_reassigned() -> None:
    result = CommandResult[None](message="Complete.")
    warning = CommandWarning("NOTICE", "Review the result.")

    with pytest.raises(FrozenInstanceError):
        result.message = "Changed."  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        warning.code = "CHANGED"  # type: ignore[misc]


def test_result_and_warning_copy_mutable_mappings() -> None:
    context = {"repository": "automation"}
    metadata = {"revision": "main"}
    warning = CommandWarning("NOTICE", "Review the result.", context)
    result = CommandResult[None](metadata=metadata, warnings=(warning,))

    context["repository"] = "changed"
    metadata["revision"] = "changed"

    assert warning.context == {"repository": "automation"}
    assert result.metadata == {"revision": "main"}
    with pytest.raises(TypeError):
        warning.context["repository"] = "changed"
    with pytest.raises(TypeError):
        result.metadata["revision"] = "changed"


@pytest.mark.parametrize("code", ["", "lowercase", "INVALID-CODE", "1_INVALID"])
def test_warning_rejects_unstable_codes(code: str) -> None:
    with pytest.raises(ValidationError, match="stable uppercase identifier"):
        CommandWarning(code, "Safe warning.")


@pytest.mark.parametrize("message", ["", " "])
def test_warning_rejects_empty_messages(message: str) -> None:
    with pytest.raises(ValidationError, match="message must be non-empty"):
        CommandWarning("NOTICE", message)


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"message": " "}, "message must be non-empty"),
        ({"changed": 1}, "changed flag must be a boolean"),
        ({"warnings": []}, "warnings must be a tuple"),
        ({"warnings": ("invalid",)}, "tuple of CommandWarning"),
        ({"metadata": []}, "metadata must be a mapping"),
    ],
)
def test_result_rejects_invalid_runtime_values(arguments: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        CommandResult(**arguments)  # type: ignore[arg-type]
