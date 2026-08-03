"""Stable error contracts shared across ansiblectl layers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from types import MappingProxyType
from typing import Any, ClassVar


class ExitCode(IntEnum):
    """Stable process exit codes exposed by the command-line interface."""

    SUCCESS = 0
    GENERAL_ERROR = 1
    USAGE_ERROR = 2
    CONFIGURATION_ERROR = 3
    VALIDATION_ERROR = 4
    EXTERNAL_TOOL_ERROR = 5
    RESOURCE_CONFLICT = 6
    AUTHENTICATION_ERROR = 7
    PLUGIN_ERROR = 8
    MIGRATION_ERROR = 9
    INTERRUPTED = 130


class ErrorCode(StrEnum):
    """Stable machine-readable identifiers for public error categories."""

    ANSIBLECTL_ERROR = "ANSIBLECTL_ERROR"
    USAGE_ERROR = "USAGE_ERROR"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    REPOSITORY_ERROR = "REPOSITORY_ERROR"
    INVENTORY_ERROR = "INVENTORY_ERROR"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    EXTERNAL_TOOL_ERROR = "EXTERNAL_TOOL_ERROR"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    SECRETS_ERROR = "SECRETS_ERROR"
    PLUGIN_ERROR = "PLUGIN_ERROR"
    MIGRATION_ERROR = "MIGRATION_ERROR"
    INFRASTRUCTURE_ERROR = "INFRASTRUCTURE_ERROR"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    OPERATION_CANCELLED = "OPERATION_CANCELLED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    WORKSPACE_ERROR = "WORKSPACE_ERROR"
    WORKSPACE_NOT_FOUND = "WORKSPACE_NOT_FOUND"
    WORKSPACE_VALIDATION_FAILED = "WORKSPACE_VALIDATION_FAILED"
    STATE_ERROR = "STATE_ERROR"
    PLAYBOOK_VALIDATION_FAILED = "PLAYBOOK_VALIDATION_FAILED"
    PLUGIN_MANIFEST_INVALID = "PLUGIN_MANIFEST_INVALID"
    SECRET_NOT_FOUND = "SECRET_NOT_FOUND"
    REPOSITORY_DIRTY_WORKTREE = "REPOSITORY_DIRTY_WORKTREE"
    REPOSITORY_REVISION_MISMATCH = "REPOSITORY_REVISION_MISMATCH"
    FILESYSTEM_TRANSACTION_ERROR = "FILESYSTEM_TRANSACTION_ERROR"
    FILESYSTEM_RECOVERY_REQUIRED = "FILESYSTEM_RECOVERY_REQUIRED"


@dataclass(frozen=True)
class ErrorDefinition:
    """Registry metadata for one stable public error code."""

    code: ErrorCode
    category: str
    exit_code: ExitCode


def _definition(code: ErrorCode, category: str, exit_code: ExitCode) -> ErrorDefinition:
    return ErrorDefinition(code=code, category=category, exit_code=exit_code)


ERROR_CODE_REGISTRY: Mapping[str, ErrorDefinition] = MappingProxyType(
    {
        definition.code.value: definition
        for definition in (
            _definition(ErrorCode.ANSIBLECTL_ERROR, "general", ExitCode.GENERAL_ERROR),
            _definition(ErrorCode.USAGE_ERROR, "usage", ExitCode.USAGE_ERROR),
            _definition(
                ErrorCode.CONFIGURATION_ERROR,
                "configuration",
                ExitCode.CONFIGURATION_ERROR,
            ),
            _definition(ErrorCode.VALIDATION_ERROR, "validation", ExitCode.VALIDATION_ERROR),
            _definition(ErrorCode.NOT_FOUND, "not_found", ExitCode.VALIDATION_ERROR),
            _definition(ErrorCode.CONFLICT, "conflict", ExitCode.RESOURCE_CONFLICT),
            _definition(ErrorCode.REPOSITORY_ERROR, "repository", ExitCode.RESOURCE_CONFLICT),
            _definition(ErrorCode.INVENTORY_ERROR, "inventory", ExitCode.VALIDATION_ERROR),
            _definition(ErrorCode.EXECUTION_ERROR, "execution", ExitCode.EXTERNAL_TOOL_ERROR),
            _definition(
                ErrorCode.EXTERNAL_TOOL_ERROR,
                "external_tool",
                ExitCode.EXTERNAL_TOOL_ERROR,
            ),
            _definition(
                ErrorCode.AUTHENTICATION_ERROR,
                "authentication",
                ExitCode.AUTHENTICATION_ERROR,
            ),
            _definition(ErrorCode.SECRETS_ERROR, "secrets", ExitCode.AUTHENTICATION_ERROR),
            _definition(ErrorCode.PLUGIN_ERROR, "plugin", ExitCode.PLUGIN_ERROR),
            _definition(ErrorCode.MIGRATION_ERROR, "migration", ExitCode.MIGRATION_ERROR),
            _definition(
                ErrorCode.INFRASTRUCTURE_ERROR,
                "infrastructure",
                ExitCode.GENERAL_ERROR,
            ),
            _definition(
                ErrorCode.PERMISSION_DENIED,
                "permission_denied",
                ExitCode.RESOURCE_CONFLICT,
            ),
            _definition(
                ErrorCode.OPERATION_CANCELLED,
                "cancelled",
                ExitCode.INTERRUPTED,
            ),
            _definition(ErrorCode.INTERNAL_ERROR, "internal", ExitCode.GENERAL_ERROR),
            _definition(ErrorCode.WORKSPACE_ERROR, "workspace", ExitCode.VALIDATION_ERROR),
            _definition(ErrorCode.WORKSPACE_NOT_FOUND, "not_found", ExitCode.VALIDATION_ERROR),
            _definition(
                ErrorCode.WORKSPACE_VALIDATION_FAILED,
                "validation",
                ExitCode.VALIDATION_ERROR,
            ),
            _definition(ErrorCode.STATE_ERROR, "state", ExitCode.RESOURCE_CONFLICT),
            _definition(
                ErrorCode.PLAYBOOK_VALIDATION_FAILED,
                "validation",
                ExitCode.VALIDATION_ERROR,
            ),
            _definition(
                ErrorCode.PLUGIN_MANIFEST_INVALID,
                "plugin",
                ExitCode.PLUGIN_ERROR,
            ),
            _definition(
                ErrorCode.SECRET_NOT_FOUND,
                "secrets",
                ExitCode.AUTHENTICATION_ERROR,
            ),
            _definition(
                ErrorCode.REPOSITORY_DIRTY_WORKTREE,
                "repository",
                ExitCode.RESOURCE_CONFLICT,
            ),
            _definition(
                ErrorCode.REPOSITORY_REVISION_MISMATCH,
                "repository",
                ExitCode.RESOURCE_CONFLICT,
            ),
            _definition(
                ErrorCode.FILESYSTEM_TRANSACTION_ERROR,
                "filesystem_transaction",
                ExitCode.RESOURCE_CONFLICT,
            ),
            _definition(
                ErrorCode.FILESYSTEM_RECOVERY_REQUIRED,
                "filesystem_recovery",
                ExitCode.RESOURCE_CONFLICT,
            ),
        )
    }
)


class AnsiblectlError(Exception):
    """Base class for all expected ansiblectl failures."""

    error_code: ClassVar[ErrorCode] = ErrorCode.ANSIBLECTL_ERROR
    exit_code: ClassVar[ExitCode] = ExitCode.GENERAL_ERROR

    def __init__(
        self,
        message: str,
        *,
        detail: str | None = None,
        hint: str | None = None,
        context: Mapping[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        if not isinstance(message, str) or not message.strip():
            raise ValueError("Public error message must be a non-empty string.")
        if detail is not None and (not isinstance(detail, str) or not detail.strip()):
            raise ValueError("Public error detail must be non-empty when provided.")
        if hint is not None and (not isinstance(hint, str) or not hint.strip()):
            raise ValueError("Public error hint must be non-empty when provided.")
        if context is not None and not isinstance(context, Mapping):
            raise TypeError("Public error context must be a mapping.")
        safe_context = dict(context or {})
        if not all(isinstance(name, str) for name in safe_context):
            raise TypeError("Public error context keys must be strings.")
        if cause is not None and not isinstance(cause, BaseException):
            raise TypeError("Public error cause must be an exception.")
        definition = ERROR_CODE_REGISTRY.get(self.error_code.value)
        if definition is None or definition.exit_code is not self.exit_code:
            raise TypeError("Public error metadata must match the stable error registry.")
        super().__init__(message)
        self.message = message
        self.detail = detail
        self.hint = hint
        self.context = MappingProxyType(safe_context)
        self.cause = cause

    @property
    def category(self) -> str:
        """Return the stable public category registered for this error."""

        return ERROR_CODE_REGISTRY[self.error_code.value].category


class DomainError(AnsiblectlError):
    """Compatibility base for expected failures in existing domain operations."""


class UsageError(AnsiblectlError):
    """Raised by a delivery boundary when command-line usage is invalid."""

    error_code = ErrorCode.USAGE_ERROR
    exit_code = ExitCode.USAGE_ERROR


class ConfigurationError(DomainError):
    """Raised when configuration cannot be safely parsed or validated."""

    error_code = ErrorCode.CONFIGURATION_ERROR
    exit_code = ExitCode.CONFIGURATION_ERROR


class ValidationError(DomainError):
    """Raised when input or generated data violates a defined contract."""

    error_code = ErrorCode.VALIDATION_ERROR
    exit_code = ExitCode.VALIDATION_ERROR


class NotFoundError(DomainError):
    """Raised when a requested object does not exist."""

    error_code = ErrorCode.NOT_FOUND
    exit_code = ExitCode.VALIDATION_ERROR


class ConflictError(DomainError):
    """Raised when target state conflicts with a requested operation."""

    error_code = ErrorCode.CONFLICT
    exit_code = ExitCode.RESOURCE_CONFLICT


class RepositoryError(DomainError):
    """Base class for safe, actionable repository failures."""

    error_code = ErrorCode.REPOSITORY_ERROR
    exit_code = ExitCode.RESOURCE_CONFLICT


class InventoryError(DomainError):
    """Raised when an inventory source cannot produce valid data."""

    error_code = ErrorCode.INVENTORY_ERROR
    exit_code = ExitCode.VALIDATION_ERROR


class ExecutionError(DomainError):
    """Raised when an execution request violates its safe contract."""

    error_code = ErrorCode.EXECUTION_ERROR
    exit_code = ExitCode.EXTERNAL_TOOL_ERROR


class ExternalToolError(DomainError):
    """Raised when a required external executable is unavailable or fails."""

    error_code = ErrorCode.EXTERNAL_TOOL_ERROR
    exit_code = ExitCode.EXTERNAL_TOOL_ERROR


class AuthenticationError(DomainError):
    """Raised when credentials are missing, rejected, or invalid."""

    error_code = ErrorCode.AUTHENTICATION_ERROR
    exit_code = ExitCode.AUTHENTICATION_ERROR


class SecretsError(DomainError):
    """Raised when secret-provider or secret-resolution operations fail."""

    error_code = ErrorCode.SECRETS_ERROR
    exit_code = ExitCode.AUTHENTICATION_ERROR


class PluginError(DomainError):
    """Raised when a plugin cannot be loaded, validated, or executed."""

    error_code = ErrorCode.PLUGIN_ERROR
    exit_code = ExitCode.PLUGIN_ERROR


class MigrationError(DomainError):
    """Raised when a required migration cannot be completed."""

    error_code = ErrorCode.MIGRATION_ERROR
    exit_code = ExitCode.MIGRATION_ERROR


class InfrastructureError(DomainError):
    """Raised when an infrastructure adapter cannot complete safe work."""

    error_code = ErrorCode.INFRASTRUCTURE_ERROR
    exit_code = ExitCode.GENERAL_ERROR


class PermissionDeniedError(DomainError):
    """Raised when operating-system or policy permissions deny an operation."""

    error_code = ErrorCode.PERMISSION_DENIED
    exit_code = ExitCode.RESOURCE_CONFLICT


class OperationCancelledError(DomainError):
    """Raised when an operation is intentionally cancelled."""

    error_code = ErrorCode.OPERATION_CANCELLED
    exit_code = ExitCode.INTERRUPTED


class InternalOperationalError(DomainError):
    """Safely represents an unexpected exception at the public boundary."""

    error_code = ErrorCode.INTERNAL_ERROR
    exit_code = ExitCode.GENERAL_ERROR


class WorkspaceError(DomainError):
    """Base class for safe, actionable workspace failures."""

    error_code = ErrorCode.WORKSPACE_ERROR
    exit_code = ExitCode.VALIDATION_ERROR


class WorkspaceNotFoundError(WorkspaceError):
    """Raised when workspace discovery cannot find valid metadata."""

    error_code = ErrorCode.WORKSPACE_NOT_FOUND
    exit_code = ExitCode.VALIDATION_ERROR


class WorkspaceValidationError(WorkspaceError):
    """Raised when workspace metadata is malformed or unsupported."""

    error_code = ErrorCode.WORKSPACE_VALIDATION_FAILED
    exit_code = ExitCode.VALIDATION_ERROR


class StateError(DomainError):
    """Raised when workspace state cannot be inspected or mutated safely."""

    error_code = ErrorCode.STATE_ERROR
    exit_code = ExitCode.RESOURCE_CONFLICT


class FilesystemTransactionError(InfrastructureError):
    """Raised when a filesystem transaction cannot complete safely."""

    error_code = ErrorCode.FILESYSTEM_TRANSACTION_ERROR
    exit_code = ExitCode.RESOURCE_CONFLICT


class FilesystemRecoveryError(InfrastructureError):
    """Raised when an interrupted transaction cannot be recovered automatically."""

    error_code = ErrorCode.FILESYSTEM_RECOVERY_REQUIRED
    exit_code = ExitCode.RESOURCE_CONFLICT


__all__ = [
    "ERROR_CODE_REGISTRY",
    "AnsiblectlError",
    "AuthenticationError",
    "ConfigurationError",
    "ConflictError",
    "DomainError",
    "ErrorCode",
    "ErrorDefinition",
    "ExecutionError",
    "ExitCode",
    "ExternalToolError",
    "FilesystemRecoveryError",
    "FilesystemTransactionError",
    "InfrastructureError",
    "InternalOperationalError",
    "InventoryError",
    "MigrationError",
    "NotFoundError",
    "OperationCancelledError",
    "PermissionDeniedError",
    "PluginError",
    "RepositoryError",
    "SecretsError",
    "StateError",
    "UsageError",
    "ValidationError",
    "WorkspaceError",
    "WorkspaceNotFoundError",
    "WorkspaceValidationError",
]
