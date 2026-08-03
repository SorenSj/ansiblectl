"""Unit tests for the stable core error contract."""

from collections.abc import Mapping

import pytest

from ansiblectl.domain.errors import (
    ERROR_CODE_REGISTRY,
    AnsiblectlError,
    AuthenticationError,
    ConfigurationError,
    ConflictError,
    ErrorCode,
    ExecutionError,
    ExitCode,
    ExternalToolError,
    InfrastructureError,
    InternalOperationalError,
    InventoryError,
    MigrationError,
    NotFoundError,
    OperationCancelledError,
    PermissionDeniedError,
    PluginError,
    RepositoryError,
    SecretsError,
    UsageError,
    ValidationError,
)


def test_base_error_preserves_public_details_and_original_cause() -> None:
    cause = ValueError("adapter detail")
    context = {"field": "repositories.default.path"}

    error = AnsiblectlError(
        "Configuration validation failed.",
        detail="The repository path must be absolute.",
        hint="Use an absolute path.",
        context=context,
        cause=cause,
    )
    context["field"] = "changed after construction"

    assert str(error) == "Configuration validation failed."
    assert error.args == ("Configuration validation failed.",)
    assert error.message == "Configuration validation failed."
    assert error.detail == "The repository path must be absolute."
    assert error.hint == "Use an absolute path."
    assert error.context == {"field": "repositories.default.path"}
    assert error.cause is cause
    assert error.error_code is ErrorCode.ANSIBLECTL_ERROR
    assert error.exit_code is ExitCode.GENERAL_ERROR
    assert error.category == "general"


def test_base_error_uses_independent_empty_contexts() -> None:
    first = AnsiblectlError("first")
    second = AnsiblectlError("second")

    assert first.context is not second.context
    with pytest.raises(TypeError):
        first.context["operation"] = "repository sync"  # type: ignore[index]
    assert second.context == {}
    assert first.detail is None
    assert first.hint is None
    assert first.cause is None


@pytest.mark.parametrize(
    ("arguments", "exception_type", "message"),
    [
        ({"message": " "}, ValueError, "message must be a non-empty"),
        ({"message": "Safe.", "detail": ""}, ValueError, "detail must be non-empty"),
        ({"message": "Safe.", "hint": " "}, ValueError, "hint must be non-empty"),
        ({"message": "Safe.", "context": []}, TypeError, "context must be a mapping"),
        ({"message": "Safe.", "context": {1: "value"}}, TypeError, "keys must be strings"),
        ({"message": "Safe.", "cause": "failure"}, TypeError, "cause must be an exception"),
    ],
)
def test_base_error_rejects_invalid_runtime_fields(
    arguments: dict[str, object], exception_type: type[Exception], message: str
) -> None:
    with pytest.raises(exception_type, match=message):
        AnsiblectlError(**arguments)  # type: ignore[arg-type]


def test_error_metadata_must_match_registry() -> None:
    class InvalidError(AnsiblectlError):
        error_code = ErrorCode.CONFLICT
        exit_code = ExitCode.GENERAL_ERROR

    with pytest.raises(TypeError, match="match the stable error registry"):
        InvalidError("Safe failure.")


@pytest.mark.parametrize(
    ("error_type", "error_code", "exit_code", "category"),
    [
        (UsageError, ErrorCode.USAGE_ERROR, ExitCode.USAGE_ERROR, "usage"),
        (
            ConfigurationError,
            ErrorCode.CONFIGURATION_ERROR,
            ExitCode.CONFIGURATION_ERROR,
            "configuration",
        ),
        (ValidationError, ErrorCode.VALIDATION_ERROR, ExitCode.VALIDATION_ERROR, "validation"),
        (NotFoundError, ErrorCode.NOT_FOUND, ExitCode.VALIDATION_ERROR, "not_found"),
        (ConflictError, ErrorCode.CONFLICT, ExitCode.RESOURCE_CONFLICT, "conflict"),
        (RepositoryError, ErrorCode.REPOSITORY_ERROR, ExitCode.RESOURCE_CONFLICT, "repository"),
        (InventoryError, ErrorCode.INVENTORY_ERROR, ExitCode.VALIDATION_ERROR, "inventory"),
        (ExecutionError, ErrorCode.EXECUTION_ERROR, ExitCode.EXTERNAL_TOOL_ERROR, "execution"),
        (
            ExternalToolError,
            ErrorCode.EXTERNAL_TOOL_ERROR,
            ExitCode.EXTERNAL_TOOL_ERROR,
            "external_tool",
        ),
        (
            AuthenticationError,
            ErrorCode.AUTHENTICATION_ERROR,
            ExitCode.AUTHENTICATION_ERROR,
            "authentication",
        ),
        (SecretsError, ErrorCode.SECRETS_ERROR, ExitCode.AUTHENTICATION_ERROR, "secrets"),
        (PluginError, ErrorCode.PLUGIN_ERROR, ExitCode.PLUGIN_ERROR, "plugin"),
        (MigrationError, ErrorCode.MIGRATION_ERROR, ExitCode.MIGRATION_ERROR, "migration"),
        (
            InfrastructureError,
            ErrorCode.INFRASTRUCTURE_ERROR,
            ExitCode.GENERAL_ERROR,
            "infrastructure",
        ),
        (
            PermissionDeniedError,
            ErrorCode.PERMISSION_DENIED,
            ExitCode.RESOURCE_CONFLICT,
            "permission_denied",
        ),
        (OperationCancelledError, ErrorCode.OPERATION_CANCELLED, ExitCode.INTERRUPTED, "cancelled"),
        (InternalOperationalError, ErrorCode.INTERNAL_ERROR, ExitCode.GENERAL_ERROR, "internal"),
    ],
)
def test_public_error_categories_have_stable_metadata(
    error_type: type[AnsiblectlError],
    error_code: ErrorCode,
    exit_code: ExitCode,
    category: str,
) -> None:
    error = error_type("safe public message")

    assert isinstance(error, AnsiblectlError)
    assert error.error_code is error_code
    assert error.exit_code is exit_code
    assert error.category == category


def test_exit_codes_match_the_documented_process_contract() -> None:
    assert {code.name: code.value for code in ExitCode} == {
        "SUCCESS": 0,
        "GENERAL_ERROR": 1,
        "USAGE_ERROR": 2,
        "CONFIGURATION_ERROR": 3,
        "VALIDATION_ERROR": 4,
        "EXTERNAL_TOOL_ERROR": 5,
        "RESOURCE_CONFLICT": 6,
        "AUTHENTICATION_ERROR": 7,
        "PLUGIN_ERROR": 8,
        "MIGRATION_ERROR": 9,
        "INTERRUPTED": 130,
    }


def test_registry_contains_every_stable_error_code_once() -> None:
    assert isinstance(ERROR_CODE_REGISTRY, Mapping)
    assert set(ERROR_CODE_REGISTRY) == {code.value for code in ErrorCode}
    assert all(key == definition.code.value for key, definition in ERROR_CODE_REGISTRY.items())


def test_registry_cannot_be_mutated() -> None:
    with pytest.raises(TypeError):
        ERROR_CODE_REGISTRY["DYNAMIC_ERROR"] = ERROR_CODE_REGISTRY["INTERNAL_ERROR"]  # type: ignore[index]
