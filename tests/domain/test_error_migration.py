"""Regression tests for concrete legacy error migration."""

import pytest

from ansiblectl.domain.errors import (
    AnsiblectlError,
    ErrorCode,
    ExitCode,
    StateError,
    WorkspaceError,
    WorkspaceNotFoundError,
    WorkspaceValidationError,
)
from ansiblectl.domain.playbook import PlaybookError
from ansiblectl.domain.plugins import PluginManifestError
from ansiblectl.domain.repository import DirtyWorktreeError, RevisionMismatchError
from ansiblectl.domain.secrets import SecretNotFoundError


@pytest.mark.parametrize(
    ("error_type", "error_code", "exit_code", "category"),
    [
        (
            WorkspaceError,
            ErrorCode.WORKSPACE_ERROR,
            ExitCode.VALIDATION_ERROR,
            "workspace",
        ),
        (
            WorkspaceNotFoundError,
            ErrorCode.WORKSPACE_NOT_FOUND,
            ExitCode.VALIDATION_ERROR,
            "not_found",
        ),
        (
            WorkspaceValidationError,
            ErrorCode.WORKSPACE_VALIDATION_FAILED,
            ExitCode.VALIDATION_ERROR,
            "validation",
        ),
        (StateError, ErrorCode.STATE_ERROR, ExitCode.RESOURCE_CONFLICT, "state"),
        (
            PlaybookError,
            ErrorCode.PLAYBOOK_VALIDATION_FAILED,
            ExitCode.VALIDATION_ERROR,
            "validation",
        ),
        (
            PluginManifestError,
            ErrorCode.PLUGIN_MANIFEST_INVALID,
            ExitCode.PLUGIN_ERROR,
            "plugin",
        ),
        (
            SecretNotFoundError,
            ErrorCode.SECRET_NOT_FOUND,
            ExitCode.AUTHENTICATION_ERROR,
            "secrets",
        ),
        (
            DirtyWorktreeError,
            ErrorCode.REPOSITORY_DIRTY_WORKTREE,
            ExitCode.RESOURCE_CONFLICT,
            "repository",
        ),
        (
            RevisionMismatchError,
            ErrorCode.REPOSITORY_REVISION_MISMATCH,
            ExitCode.RESOURCE_CONFLICT,
            "repository",
        ),
    ],
)
def test_existing_error_has_stable_phase_one_metadata(
    error_type: type[AnsiblectlError],
    error_code: ErrorCode,
    exit_code: ExitCode,
    category: str,
) -> None:
    error = error_type("Safe message.")

    assert error.error_code is error_code
    assert error.exit_code is exit_code
    assert error.category == category
