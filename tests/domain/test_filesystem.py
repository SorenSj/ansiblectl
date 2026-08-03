"""Domain tests for filesystem capability contracts."""

import pytest

from ansiblectl.domain.filesystem import (
    MAX_RECOVERY_AGE_SECONDS,
    FilesystemCapabilityReason,
    FilesystemCapabilityReport,
    RecoveryAction,
    RecoveryDiagnostic,
    RecoveryReason,
)


def test_supported_capability_report_has_stable_schema() -> None:
    report = FilesystemCapabilityReport(True, "darwin", "filesystem:opaque")

    assert report.schema_version == 1
    assert report.reasons == ()


def test_unsupported_capability_report_requires_reasons() -> None:
    report = FilesystemCapabilityReport(
        False,
        "linux",
        "filesystem:opaque",
        (FilesystemCapabilityReason.ADVISORY_LOCKING_UNAVAILABLE,),
    )

    assert report.supported is False
    assert report.reasons == (FilesystemCapabilityReason.ADVISORY_LOCKING_UNAVAILABLE,)


@pytest.mark.parametrize(
    "report",
    [
        FilesystemCapabilityReport,
    ],
)
def test_capability_report_rejects_inconsistent_runtime_values(
    report: type[FilesystemCapabilityReport],
) -> None:
    with pytest.raises(ValueError, match="agree"):
        report(True, "linux", "filesystem:opaque", (FilesystemCapabilityReason.POSIX_REQUIRED,))
    with pytest.raises(ValueError, match="scope identifier"):
        report(True, "linux", None)
    with pytest.raises(ValueError, match="platform"):
        report(False, " ", None, (FilesystemCapabilityReason.POSIX_REQUIRED,))
    with pytest.raises(ValueError, match="schema version"):
        report(False, "linux", None, (FilesystemCapabilityReason.POSIX_REQUIRED,), 2)


def test_recovery_diagnostic_accepts_only_bounded_safe_metadata() -> None:
    diagnostic = RecoveryDiagnostic(
        "opaque-id",
        "committing",
        MAX_RECOVERY_AGE_SECONDS,
        RecoveryAction.ROLLBACK,
        (RecoveryReason.ROLLBACK_REQUIRED,),
        False,
    )

    assert diagnostic.schema_version == 1
    with pytest.raises(ValueError, match="bounded"):
        RecoveryDiagnostic(
            "opaque-id",
            "committing",
            -1.0,
            RecoveryAction.ROLLBACK,
            (RecoveryReason.ROLLBACK_REQUIRED,),
            False,
        )
    with pytest.raises(ValueError, match="reasons"):
        RecoveryDiagnostic("opaque-id", "committing", None, RecoveryAction.ROLLBACK, (), False)
