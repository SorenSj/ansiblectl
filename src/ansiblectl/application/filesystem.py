"""Application service for explicit filesystem recovery."""

from dataclasses import dataclass

from ansiblectl.domain.filesystem import (
    FilesystemRecoveryPort,
    FilesystemRecoveryResult,
    RecoveryDiagnostic,
)


@dataclass(frozen=True)
class FilesystemRecoveryService:
    """Preview or apply recovery without exposing journal contents."""

    port: FilesystemRecoveryPort

    def recover(self, *, apply: bool = False) -> FilesystemRecoveryResult:
        transaction_ids = self.port.pending()
        if apply and transaction_ids:
            self.port.recover()
        return FilesystemRecoveryResult(transaction_ids, apply)

    def diagnostics(self) -> tuple[RecoveryDiagnostic, ...]:
        """Return safe diagnostic projections without applying recovery."""

        return self.port.diagnostics()
