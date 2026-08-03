"""Construct concrete application dependencies at the CLI boundary."""

import os
from pathlib import Path

from ansiblectl import __version__
from ansiblectl.application.execution import ExecutionService
from ansiblectl.application.execution_history import ExecutionHistoryService
from ansiblectl.application.inventory import InventoryService
from ansiblectl.application.playbook import PlaybookValidationService
from ansiblectl.application.plugins import PluginDiscoveryService
from ansiblectl.application.policy import PolicyService
from ansiblectl.application.repository import RepositoryService
from ansiblectl.application.run import RunService
from ansiblectl.application.standard_policies import (
    ApplyRequiresCleanRepositoryPolicy,
    ApplyRequiresLimitPolicy,
)
from ansiblectl.application.status import DefaultStatusService, StatusService
from ansiblectl.application.workspace import WorkspaceService
from ansiblectl.domain.events import EventBus
from ansiblectl.domain.inventory import InventoryError
from ansiblectl.infrastructure.execution_history import JsonLinesExecutionHistory
from ansiblectl.infrastructure.generated_inventory import materialize_inventory
from ansiblectl.infrastructure.git_repository import GitRepositoryAdapter
from ansiblectl.infrastructure.json_logging import EventLogSubscriber, JsonLinesLogSink
from ansiblectl.infrastructure.local_execution import LocalExecutionAdapter
from ansiblectl.infrastructure.local_workspace_store import LocalWorkspaceStore
from ansiblectl.infrastructure.plugin_manifests import discover_manifests
from ansiblectl.infrastructure.yaml_inventory import YamlInventoryProvider


def build_status_service() -> StatusService:
    """Create the status use case and its dependencies for a CLI invocation."""

    return DefaultStatusService(version=__version__)


def build_workspace_service() -> WorkspaceService:
    """Create the local workspace use cases for a CLI invocation."""

    return WorkspaceService(store=LocalWorkspaceStore())


def build_repository_service() -> RepositoryService:
    """Create repository operations with the local Git adapter."""

    return RepositoryService(port=GitRepositoryAdapter())


def build_plugin_discovery_service() -> PluginDiscoveryService:
    """Create safe file-based plugin manifest discovery."""

    return PluginDiscoveryService(file_loader=discover_manifests)


def build_playbook_validation_service() -> PlaybookValidationService:
    """Create selection validation with explicit tool provenance."""

    return PlaybookValidationService(validator_version=__version__)


def build_run_service(workspace_root: Path, inventory_source: Path | None = None) -> RunService:
    """Create check-mode Ansible execution from concrete local adapters."""

    event_log = JsonLinesLogSink(workspace_root)
    events = EventBus([EventLogSubscriber(event_log)])
    return RunService(
        inventory=build_inventory_service(workspace_root, inventory_source),
        execution=ExecutionService(LocalExecutionAdapter(), events),
        policy=PolicyService([ApplyRequiresLimitPolicy(), ApplyRequiresCleanRepositoryPolicy()]),
        materialize_inventory=materialize_inventory,
        repository=build_repository_service(),
    )


def build_execution_history_service(workspace_root: Path) -> ExecutionHistoryService:
    """Create read-only inspection of safe workspace execution records."""

    return ExecutionHistoryService(JsonLinesExecutionHistory(workspace_root))


def execution_environment() -> dict[str, str]:
    """Return the explicit environment allowlist for local execution."""

    allowed = {"ANSIBLE_CONFIG", "HOME", "LANG", "LC_ALL", "PATH", "SSH_AUTH_SOCK", "USER"}
    return {name: value for name, value in os.environ.items() if name in allowed}


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
