"""Workspace event archive selection and target contract tests."""

from dataclasses import replace

import pytest

from ansiblectl.domain.durable_events import DurableEventEnvelope
from ansiblectl.domain.event_archive import (
    MAX_EVENT_ARCHIVE_SEQUENCE,
    WorkspaceEventArchive,
    validate_event_archive_id,
)


def envelope(sequence: int = 7) -> DurableEventEnvelope:
    return DurableEventEnvelope(
        "00000000Z80000000000000000",
        sequence,
        "workspace.initialized",
        "2026-08-04T00:00:00.000000Z",
        None,
        {"project_name": "demo"},
    )


@pytest.mark.parametrize("archive_id", ["audit", "audit.primary", "a-1", "a_1", "a" * 128])
def test_archive_accepts_only_canonical_logical_identifiers(archive_id: str) -> None:
    archive = WorkspaceEventArchive(archive_id)

    assert archive.archive_id == archive_id
    assert validate_event_archive_id(archive_id) == archive_id
    assert archive_id not in repr(archive)


@pytest.mark.parametrize(
    "archive_id",
    [
        None,
        True,
        1,
        "",
        "Audit",
        "audit archive",
        "audit/archive",
        r"audit\archive",
        ".",
        "..",
        "../audit",
        "/audit",
        "audit/",
        "åudit",
        "a" * 129,
    ],
)
def test_archive_rejects_paths_and_noncanonical_identifiers(archive_id: object) -> None:
    with pytest.raises(ValueError, match="not canonical"):
        WorkspaceEventArchive(archive_id)  # type: ignore[arg-type]


@pytest.mark.parametrize("sequence", [1, 7, MAX_EVENT_ARCHIVE_SEQUENCE])
def test_archive_binds_sequence_and_event_id_to_exact_filename(sequence: int) -> None:
    target = WorkspaceEventArchive("audit.primary").target_for(envelope(sequence))

    assert target.archive_id == "audit.primary"
    assert target.filename == (f"{sequence:020d}-00000000Z80000000000000000.json")
    representation = repr(target)
    assert "audit.primary" not in representation
    assert "00000000Z80000000000000000" not in representation


def test_archive_rejects_non_envelope_and_sequence_beyond_filename_bound() -> None:
    archive = WorkspaceEventArchive("audit")

    with pytest.raises(ValueError, match="durable event envelope"):
        archive.target_for(object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="sequence exceeds"):
        archive.target_for(replace(envelope(), sequence=MAX_EVENT_ARCHIVE_SEQUENCE + 1))
