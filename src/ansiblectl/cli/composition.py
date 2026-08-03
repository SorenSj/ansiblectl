"""Construct concrete application dependencies at the CLI boundary."""

from pathlib import Path

from ansiblectl import __version__
from ansiblectl.application.inventory import InventoryService
from ansiblectl.application.status import DefaultStatusService, StatusService
from ansiblectl.application.workspace import WorkspaceService
from ansiblectl.domain.inventory import InventoryError
from ansiblectl.infrastructure.local_workspace_store import LocalWorkspaceStore
from ansiblectl.infrastructure.yaml_inventory import YamlInventoryProvider


def build_status_service() -> StatusService:
    """Create the status use case and its dependencies for a CLI invocation."""

    return DefaultStatusService(version=__version__)


def build_workspace_service() -> WorkspaceService:
    """Create the local workspace use cases for a CLI invocation."""

    return WorkspaceService(store=LocalWorkspaceStore())


def build_inventory_service(
    workspace_root: Path | None = None, source: Path | None = None
) -> InventoryService:
    """Create inventory resolution with the currently configured providers."""

    if workspace_root is None:
        return InventoryService(providers=[])
    root = workspace_root.resolve()
    identifier = source or Path("inventory/hosts.yml")
    candidate = (
        (root / identifier).resolve() if not identifier.is_absolute() else identifier.resolve()
    )
    if not candidate.is_relative_to(root):
        raise InventoryError("Inventory source must remain inside the selected workspace.")
    return InventoryService(providers=[YamlInventoryProvider(candidate)])
