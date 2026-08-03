"""Compatibility tests for the public error import surface."""

import ansiblectl.errors as public_errors
from ansiblectl.domain import errors as domain_errors


def test_public_error_module_exports_only_the_documented_contract() -> None:
    assert set(public_errors.__all__) == {
        "ERROR_CODE_REGISTRY",
        "AnsiblectlError",
        "AuthenticationError",
        "ConfigurationError",
        "ConflictError",
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
        "UsageError",
        "ValidationError",
    }


def test_public_error_types_are_the_canonical_domain_types() -> None:
    for name in public_errors.__all__:
        assert getattr(public_errors, name) is getattr(domain_errors, name)
