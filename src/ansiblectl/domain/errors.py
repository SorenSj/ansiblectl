"""Typed failures that can cross layer boundaries safely."""


class DomainError(Exception):
    """Base class for expected failures caused by invalid domain operations."""


class WorkspaceError(DomainError):
    """Base class for safe, actionable workspace failures."""


class WorkspaceNotFoundError(WorkspaceError):
    """Raised when workspace discovery cannot find valid metadata."""


class WorkspaceValidationError(WorkspaceError):
    """Raised when workspace metadata is malformed or unsupported."""


class ConfigurationError(DomainError):
    """Raised when configuration cannot be safely parsed or validated."""


class ExecutionError(DomainError):
    """Raised when an execution request violates its safe contract."""


class StateError(DomainError):
    """Raised when workspace state cannot be inspected or mutated safely."""
