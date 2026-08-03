"""Construct concrete application dependencies at the CLI boundary."""

from ansiblectl import __version__
from ansiblectl.application.inventory import InventoryService
from ansiblectl.application.status import DefaultStatusService, StatusService
from ansiblectl.application.workspace import WorkspaceService
from ansiblectl.infrastructure.local_workspace_store import LocalWorkspaceStore


def build_status_service() -> StatusService:
    """Create the status use case and its dependencies for a CLI invocation."""

    return DefaultStatusService(version=__version__)


def build_workspace_service() -> WorkspaceService:
    """Create the local workspace use cases for a CLI invocation."""

    return WorkspaceService(store=LocalWorkspaceStore())


def build_inventory_service() -> InventoryService:
    """Create inventory resolution with the currently configured providers."""

    return InventoryService(providers=[])
