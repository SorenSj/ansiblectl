"""Workspace webhook configuration loading tests."""

from pathlib import Path

import pytest

from ansiblectl.domain.errors import ConfigurationError
from ansiblectl.infrastructure.webhook_configuration import load_webhook_endpoints


def test_missing_configuration_has_no_implicit_endpoints(tmp_path: Path) -> None:
    assert load_webhook_endpoints(tmp_path) == {}


def test_loader_reads_private_workspace_endpoint_configuration(tmp_path: Path) -> None:
    private = tmp_path / ".ansiblectl"
    private.mkdir()
    (private / "webhooks.yaml").write_text(
        """schema_version: 1
endpoints:
  audit:
    url: https://hooks.example.test/events
    allowed_hostnames: [hooks.example.test]
""",
        encoding="utf-8",
    )

    endpoint = load_webhook_endpoints(tmp_path)["audit"]

    assert endpoint.hostname == "hooks.example.test"
    assert endpoint.bearer_secret is None
    assert endpoint.connect_timeout_seconds == 10
    assert endpoint.read_timeout_seconds == 30


def test_loader_rejects_symlink_escape_and_non_mapping_yaml(tmp_path: Path) -> None:
    private = tmp_path / ".ansiblectl"
    private.mkdir()
    outside = tmp_path.parent / "outside-webhooks.yaml"
    outside.write_text("schema_version: 1\nendpoints: {}\n", encoding="utf-8")
    (private / "webhooks.yaml").symlink_to(outside)

    with pytest.raises(ConfigurationError, match="inside the workspace"):
        load_webhook_endpoints(tmp_path)

    (private / "webhooks.yaml").unlink()
    (private / "webhooks.yaml").write_text("- invalid\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="YAML mapping"):
        load_webhook_endpoints(tmp_path)
