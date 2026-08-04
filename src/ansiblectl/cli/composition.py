"""Construct concrete application dependencies at the CLI boundary."""

import os
from pathlib import Path

from ansiblectl import __version__
from ansiblectl.application.configuration import ConfigurationService
from ansiblectl.application.event_operations import EventOperationsService
from ansiblectl.application.execution import ExecutionService
from ansiblectl.application.execution_history import ExecutionHistoryService
from ansiblectl.application.filesystem import FilesystemRecoveryService
from ansiblectl.application.inventory import InventoryService, InventoryValidationService
from ansiblectl.application.playbook import PlaybookValidationService
from ansiblectl.application.plugins import PluginDiscoveryService
from ansiblectl.application.policy import PolicyService
from ansiblectl.application.repository import RepositoryService
from ansiblectl.application.run import RunService
from ansiblectl.application.standard_policies import (
    ApplyRequiresCleanRepositoryPolicy,
    ApplyRequiresLimitPolicy,
)
from ansiblectl.application.state import StateService
from ansiblectl.application.status import DefaultStatusService, StatusService
from ansiblectl.application.workspace import WorkspaceService
from ansiblectl.domain.errors import ExecutionError
from ansiblectl.domain.events import EventBus
from ansiblectl.domain.inventory import InventoryError
from ansiblectl.domain.workspace import (
    WORKSPACE_DIRECTORY,
    WORKSPACE_METADATA_FILENAME,
    WORKSPACE_SCHEMA_VERSION,
    Workspace,
)
from ansiblectl.infrastructure.event_outbox import SqliteEventOutbox
from ansiblectl.infrastructure.event_outbox_subscriber import (
    EventOutboxSubscriber,
    WorkspaceEventOutboxSubscriber,
)
from ansiblectl.infrastructure.execution_history import JsonLinesExecutionHistory
from ansiblectl.infrastructure.generated_inventory import materialize_inventory
from ansiblectl.infrastructure.git_repository import GitRepositoryAdapter
from ansiblectl.infrastructure.json_logging import EventLogSubscriber, JsonLinesLogSink
from ansiblectl.infrastructure.local_execution import LocalExecutionAdapter
from ansiblectl.infrastructure.local_workspace_store import LocalWorkspaceStore
from ansiblectl.infrastructure.plugin_manifests import (
    discover_manifest_directory,
    discover_manifests,
)
from ansiblectl.infrastructure.transactional_filesystem import TransactionalFilesystem
from ansiblectl.infrastructure.workspace_state import WorkspaceStateStore
from ansiblectl.infrastructure.yaml_configuration import LocalConfigurationSourceProvider
from ansiblectl.infrastructure.yaml_inventory import YamlInventoryProvider


def build_status_service() -> StatusService:
    """Create the status use case and its dependencies for a CLI invocation."""

    return DefaultStatusService(version=__version__)


def build_workspace_service() -> WorkspaceService:
    """Create the local workspace use cases for a CLI invocation."""

    return WorkspaceService(
        store=LocalWorkspaceStore(), events=EventBus([WorkspaceEventOutboxSubscriber()])
    )


def build_configuration_service(workspace: Workspace) -> ConfigurationService:
    """Create typed local configuration resolution for one workspace."""

    environment = {
        name: value for name, value in os.environ.items() if name == "ANSIBLECTL_LOG_LEVEL"
    }
    return ConfigurationService(LocalConfigurationSourceProvider(workspace, environment))


def build_state_service(workspace_root: Path) -> StateService:
    """Create safe workspace-state inspection."""

    return StateService(WorkspaceStateStore(workspace_root))


def build_filesystem_recovery_service(workspace_root: Path) -> FilesystemRecoveryService:
    """Create explicit recovery for interrupted workspace transactions."""

    return FilesystemRecoveryService(TransactionalFilesystem(workspace_root))


def build_repository_service() -> RepositoryService:
    """Create repository operations with the local Git adapter."""

    return RepositoryService(port=GitRepositoryAdapter())


def build_plugin_discovery_service() -> PluginDiscoveryService:
    """Create safe file-based plugin manifest discovery."""

    return PluginDiscoveryService(
        file_loader=discover_manifests,
        directory_loader=discover_manifest_directory,
    )


def build_playbook_validation_service(workspace_root: Path) -> PlaybookValidationService:
    """Create selection validation with explicit tool provenance."""

    return PlaybookValidationService(
        validator_version=__version__,
        syntax_port=ExecutionService(LocalExecutionAdapter(), _workspace_event_bus(workspace_root)),
    )


def build_run_service(workspace_root: Path, inventory_source: Path | None = None) -> RunService:
    """Create check-mode Ansible execution from concrete local adapters."""

    root = workspace_root.resolve()
    workspace = Workspace(
        root,
        root / WORKSPACE_DIRECTORY / WORKSPACE_METADATA_FILENAME,
        WORKSPACE_SCHEMA_VERSION,
    )
    return RunService(
        inventory=build_inventory_service(workspace_root, inventory_source),
        execution=ExecutionService(LocalExecutionAdapter(), _workspace_event_bus(workspace_root)),
        policy=PolicyService([ApplyRequiresLimitPolicy(), ApplyRequiresCleanRepositoryPolicy()]),
        materialize_inventory=materialize_inventory,
        repository=build_repository_service(),
        configuration=build_configuration_service(workspace),
    )


def build_execution_history_service(workspace_root: Path) -> ExecutionHistoryService:
    """Create read-only inspection of safe workspace execution records."""

    return ExecutionHistoryService(JsonLinesExecutionHistory(workspace_root))


def build_event_operations_service(workspace_root: Path) -> EventOperationsService:
    """Create durable-event operator use cases for one workspace."""

    return EventOperationsService(SqliteEventOutbox(workspace_root))


def execution_environment(workspace_root: Path) -> dict[str, str]:
    """Return the explicit environment allowlist for local execution."""

    allowed = {"ANSIBLE_CONFIG", "HOME", "LANG", "LC_ALL", "PATH", "SSH_AUTH_SOCK", "USER"}
    environment = {name: value for name, value in os.environ.items() if name in allowed}
    root = workspace_root.resolve()
    private_root = root / ".ansiblectl"
    try:
        private_root.mkdir(mode=0o700, exist_ok=True)
        if not private_root.resolve().is_relative_to(root):
            raise ExecutionError("Ansiblectl runtime paths must remain inside the workspace.")
        local_temp = private_root / "tmp"
        local_temp.mkdir(mode=0o700, exist_ok=True)
        if not local_temp.resolve().is_relative_to(root):
            raise ExecutionError("Ansible local temp must remain inside the workspace.")
        private_root.chmod(0o700)
        local_temp.chmod(0o700)
    except OSError as error:
        raise ExecutionError("Ansible local temp could not be prepared safely.") from error
    environment["ANSIBLE_LOCAL_TEMP"] = str(local_temp.resolve())
    return environment


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


def build_inventory_validation_service(
    workspace_root: Path, source: Path | None = None
) -> InventoryValidationService:
    """Create native Ansible inventory validation with private execution evidence."""

    return InventoryValidationService(
        build_inventory_service(workspace_root, source),
        ExecutionService(LocalExecutionAdapter(), _workspace_event_bus(workspace_root)),
        materialize_inventory,
    )


def _workspace_event_bus(workspace_root: Path) -> EventBus:
    """Compose independent audit-history and durable-delivery subscribers."""

    return EventBus(
        [
            EventLogSubscriber(JsonLinesLogSink(workspace_root)),
            EventOutboxSubscriber(SqliteEventOutbox(workspace_root)),
        ]
    )
