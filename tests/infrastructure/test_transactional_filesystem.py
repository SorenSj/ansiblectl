"""Tests for durable transactional filesystem operations."""

import json
from pathlib import Path

import pytest

from ansiblectl.domain.errors import FilesystemRecoveryError, FilesystemTransactionError
from ansiblectl.infrastructure.memory_logging import MemoryLogSink
from ansiblectl.infrastructure.transactional_filesystem import TransactionalFilesystem


def test_commit_applies_staged_writes_and_deletes(tmp_path: Path) -> None:
    (tmp_path / "old").write_text("old", encoding="utf-8")
    transaction = TransactionalFilesystem(tmp_path).begin()
    transaction.stage_write(Path("nested/new"), b"new")
    transaction.stage_delete(Path("old"))

    transaction.commit()

    assert (tmp_path / "nested/new").read_bytes() == b"new"
    assert not (tmp_path / "old").exists()
    assert list((tmp_path / ".ansiblectl/transactions").glob("[!.]*")) == []


def test_rollback_discards_staged_changes(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_text("before", encoding="utf-8")
    transaction = TransactionalFilesystem(tmp_path).begin()
    transaction.stage_write(Path("target"), b"after")

    transaction.rollback()

    assert target.read_text(encoding="utf-8") == "before"


def test_commit_failure_rolls_back_already_applied_operations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.write_text("before-1", encoding="utf-8")
    second.write_text("before-2", encoding="utf-8")
    transaction = TransactionalFilesystem(tmp_path).begin()
    transaction.stage_write(Path("first"), b"after-1")
    transaction.stage_write(Path("second"), b"after-2")
    original_apply = transaction._apply

    def fail_second(index: int, operation: dict[str, object]) -> None:
        if index == 1:
            raise OSError("simulated write failure")
        original_apply(index, operation)

    monkeypatch.setattr(transaction, "_apply", fail_second)

    with pytest.raises(FilesystemTransactionError, match="rolled back"):
        transaction.commit()

    assert first.read_text(encoding="utf-8") == "before-1"
    assert second.read_text(encoding="utf-8") == "before-2"


def test_recovery_restores_an_interrupted_applied_write(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_text("before", encoding="utf-8")
    filesystem = TransactionalFilesystem(tmp_path)
    transaction = filesystem.begin()
    transaction.stage_write(Path("target"), b"after")
    transaction._persist("committing")
    transaction._apply(0, transaction.operations[0])
    transaction._persist("committing")
    transaction._release_active()

    assert filesystem.pending() == (transaction.transaction_id,)

    result = filesystem.recover()

    assert result.rolled_back == (transaction.transaction_id,)
    assert target.read_text(encoding="utf-8") == "before"


def test_recovery_rejects_corrupt_journal_without_deleting_it(tmp_path: Path) -> None:
    directory = tmp_path / ".ansiblectl/transactions/broken"
    directory.mkdir(parents=True)
    (directory / "journal.json").write_text("not json", encoding="utf-8")

    with pytest.raises(FilesystemRecoveryError, match="unreadable"):
        TransactionalFilesystem(tmp_path).recover()

    assert directory.exists()


def test_recovery_cleans_journal_left_after_durable_commit(tmp_path: Path) -> None:
    filesystem = TransactionalFilesystem(tmp_path)
    transaction = filesystem.begin()
    transaction.stage_write(Path("committed"), b"value")
    transaction._persist("committing")
    transaction._apply(0, transaction.operations[0])
    transaction._persist("committed")
    transaction._release_active()

    assert filesystem.pending() == (transaction.transaction_id,)

    result = filesystem.recover()

    assert result.rolled_back == ()
    assert (tmp_path / "committed").read_bytes() == b"value"
    assert filesystem.pending() == ()


def test_recovery_ignores_transaction_owned_by_a_live_process(tmp_path: Path) -> None:
    filesystem = TransactionalFilesystem(tmp_path)
    transaction = filesystem.begin()
    transaction.stage_write(Path("active"), b"value")

    assert filesystem.pending() == ()
    assert filesystem.recover().rolled_back == ()

    transaction.rollback()


def test_write_ahead_intent_is_safe_if_process_stops_before_target_change(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_text("before", encoding="utf-8")
    filesystem = TransactionalFilesystem(tmp_path)
    transaction = filesystem.begin()
    transaction.stage_write(Path("target"), b"after")
    operation = transaction.operations[0]
    backup = transaction.directory / "backup-0"
    backup.write_bytes(target.read_bytes())
    operation["backup"] = str(backup)
    operation["applied"] = True
    transaction._persist("committing")
    transaction._release_active()

    assert filesystem.recover().rolled_back == (transaction.transaction_id,)
    assert target.read_text(encoding="utf-8") == "before"


def test_recovery_is_retryable_if_journaling_fails_after_backup_restore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.write_text("before", encoding="utf-8")
    filesystem = TransactionalFilesystem(tmp_path)
    transaction = filesystem.begin()
    transaction.stage_write(Path("target"), b"after")
    transaction._persist("committing")
    transaction._apply(0, transaction.operations[0])
    original_persist = transaction._persist

    def interrupt_after_restore(state: str) -> None:
        if state == "rolling_back":
            raise OSError("simulated crash before rollback journal update")
        original_persist(state)

    monkeypatch.setattr(transaction, "_persist", interrupt_after_restore)
    with pytest.raises(FilesystemTransactionError, match="rollback failed"):
        transaction.rollback()
    assert target.read_text(encoding="utf-8") == "before"
    assert Path(transaction.operations[0]["backup"]).exists()
    monkeypatch.setattr(transaction, "_persist", original_persist)
    transaction._release_active()

    assert filesystem.recover().rolled_back == (transaction.transaction_id,)
    assert target.read_text(encoding="utf-8") == "before"


def test_targets_cannot_escape_root_or_modify_control_data(tmp_path: Path) -> None:
    transaction = TransactionalFilesystem(tmp_path).begin()
    with pytest.raises(FilesystemTransactionError, match="escapes"):
        transaction.stage_write(Path("../outside"), b"bad")
    with pytest.raises(FilesystemTransactionError, match="reserved"):
        transaction.stage_delete(Path(".ansiblectl/transactions/data"))


def test_commit_rejects_parent_replaced_by_symlink_after_staging(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    parent = workspace / "safe"
    parent.mkdir(parents=True)
    outside.mkdir()
    transaction = TransactionalFilesystem(workspace).begin()
    transaction.stage_write(Path("safe/file"), b"must-stay-inside")
    parent.rmdir()
    parent.symlink_to(outside, target_is_directory=True)

    with pytest.raises(FilesystemTransactionError, match="rolled back"):
        transaction.commit()

    assert not (outside / "file").exists()


def test_audit_events_are_correlated_and_contain_no_file_content(tmp_path: Path) -> None:
    sink = MemoryLogSink()
    transaction = TransactionalFilesystem(tmp_path, audit_sink=sink).begin(correlation_id="run-1")
    transaction.stage_write(Path("secret"), b"do-not-log")
    transaction.commit()

    encoded = json.dumps(sink.records)
    assert "filesystem.transaction.started" in encoded
    assert "filesystem.transaction.committed" in encoded
    assert "run-1" in encoded
    assert "do-not-log" not in encoded
