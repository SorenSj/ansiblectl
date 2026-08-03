"""Application tests for explicit filesystem recovery."""

from dataclasses import dataclass, field

from ansiblectl.application.filesystem import FilesystemRecoveryService


@dataclass
class FakeRecoveryPort:
    identifiers: tuple[str, ...]
    calls: list[str] = field(default_factory=list)

    def pending(self) -> tuple[str, ...]:
        self.calls.append("pending")
        return self.identifiers

    def recover(self) -> object:
        self.calls.append("recover")
        return object()


def test_recovery_preview_is_read_only() -> None:
    port = FakeRecoveryPort(("one", "two"))

    result = FilesystemRecoveryService(port).recover()

    assert result.transaction_ids == ("one", "two")
    assert result.applied is False
    assert port.calls == ["pending"]


def test_recovery_apply_invokes_port_only_when_work_is_pending() -> None:
    pending = FakeRecoveryPort(("one",))
    empty = FakeRecoveryPort(())

    assert FilesystemRecoveryService(pending).recover(apply=True).applied is True
    assert FilesystemRecoveryService(empty).recover(apply=True).applied is True
    assert pending.calls == ["pending", "recover"]
    assert empty.calls == ["pending"]
