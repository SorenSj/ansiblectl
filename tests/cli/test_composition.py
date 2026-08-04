"""Concrete CLI composition tests."""

import stat
from pathlib import Path

import pytest

from ansiblectl.application.event_delivery import EventDeliveryService
from ansiblectl.application.standard_policies import (
    ApplyRequiresCleanRepositoryPolicy,
    ApplyRequiresLimitPolicy,
)
from ansiblectl.cli.composition import (
    build_configuration_service,
    build_run_service,
    build_state_service,
    build_webhook_delivery_service,
    build_workspace_service,
    execution_environment,
)
from ansiblectl.domain.errors import ConfigurationError, ExecutionError
from ansiblectl.domain.workspace import Workspace
from ansiblectl.infrastructure.environment_secrets import EnvironmentSecretProvider
from ansiblectl.infrastructure.event_outbox import SqliteEventOutbox
from ansiblectl.infrastructure.event_outbox_subscriber import EventOutboxSubscriber
from ansiblectl.infrastructure.json_logging import EventLogSubscriber, JsonLinesLogSink
from ansiblectl.infrastructure.webhook_delivery import HttpsWebhookDeliveryAdapter
from ansiblectl.infrastructure.workspace_state import WorkspaceStateStore
from ansiblectl.infrastructure.yaml_configuration import LocalConfigurationSourceProvider


def test_run_service_wires_execution_events_to_workspace_log(tmp_path: Path) -> None:
    service = build_run_service(tmp_path)

    assert service.execution.events is not None
    subscriber = service.execution.events.subscribers[0]
    assert isinstance(subscriber, EventLogSubscriber)
    assert isinstance(subscriber.sink, JsonLinesLogSink)
    assert subscriber.sink.path == tmp_path / ".ansiblectl" / "logs" / "events.jsonl"
    outbox_subscriber = service.execution.events.subscribers[1]
    assert isinstance(outbox_subscriber, EventOutboxSubscriber)
    assert isinstance(outbox_subscriber.outbox, SqliteEventOutbox)
    assert len(service.policy.policies) == 2
    assert isinstance(service.policy.policies[0], ApplyRequiresLimitPolicy)
    assert isinstance(service.policy.policies[1], ApplyRequiresCleanRepositoryPolicy)
    assert service.repository is not None
    assert service.configuration is not None
    assert isinstance(service.configuration.source_provider, LocalConfigurationSourceProvider)


def test_workspace_initialization_writes_path_free_durable_event(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"

    build_workspace_service().initialize(workspace_root)

    events = SqliteEventOutbox(workspace_root).read_all()
    assert len(events) == 1
    assert events[0].name == "workspace.initialized"
    assert events[0].payload == {}


def test_execution_environment_uses_private_workspace_local_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANSIBLE_LOCAL_TEMP", "/untrusted/external-temp")

    environment = execution_environment(tmp_path)

    local_temp = tmp_path / ".ansiblectl/tmp"
    assert environment["ANSIBLE_LOCAL_TEMP"] == str(local_temp)
    assert stat.S_IMODE(local_temp.stat().st_mode) == 0o700
    assert stat.S_IMODE(local_temp.parent.stat().st_mode) == 0o700


def test_execution_environment_rejects_runtime_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-runtime"
    outside.mkdir(exist_ok=True)
    (tmp_path / ".ansiblectl").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ExecutionError, match="remain inside"):
        execution_environment(tmp_path)


def test_configuration_service_receives_only_documented_environment_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANSIBLECTL_LOG_LEVEL", "debug")
    monkeypatch.setenv("ANSIBLECTL_UNDOCUMENTED", "ignored")
    workspace = Workspace(tmp_path, tmp_path / ".ansiblectl/workspace.json", 1)

    service = build_configuration_service(workspace)

    assert isinstance(service.source_provider, LocalConfigurationSourceProvider)
    assert service.source_provider.environment == {"ANSIBLECTL_LOG_LEVEL": "debug"}


def test_state_service_uses_workspace_scoped_store(tmp_path: Path) -> None:
    service = build_state_service(tmp_path)

    assert isinstance(service.port, WorkspaceStateStore)
    assert service.inspect() == ()


def test_webhook_delivery_composition_selects_one_exact_endpoint(tmp_path: Path) -> None:
    private = tmp_path / ".ansiblectl"
    private.mkdir()
    (private / "webhooks.yaml").write_text(
        """schema_version: 1
endpoints:
  primary:
    url: https://hooks.example.test/events
    allowed_hostnames: [hooks.example.test]
""",
        encoding="utf-8",
    )

    service = build_webhook_delivery_service(tmp_path, "primary")

    assert isinstance(service, EventDeliveryService)
    assert isinstance(service.adapter, HttpsWebhookDeliveryAdapter)
    assert isinstance(service.adapter.secrets, EnvironmentSecretProvider)
    with pytest.raises(ConfigurationError, match="not configured"):
        build_webhook_delivery_service(tmp_path, "missing")
