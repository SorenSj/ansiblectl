"""Safe private webhook network policy loading tests."""

from pathlib import Path

import pytest

from ansiblectl.domain.errors import ConfigurationError
from ansiblectl.infrastructure.webhook_network_policy_configuration import (
    MAX_WEBHOOK_NETWORK_POLICY_BYTES,
    load_webhook_network_policies,
)


def write_policy(path: Path, content: str) -> None:
    path.parent.mkdir(exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_missing_document_returns_no_implicit_policy(tmp_path: Path) -> None:
    assert load_webhook_network_policies(tmp_path) == {}


def test_loader_reads_one_strict_private_policy(tmp_path: Path) -> None:
    path = tmp_path / ".ansiblectl/webhook-network-policies.yaml"
    write_policy(
        path,
        """schema_version: 1
policies:
  receiver:
    allowed_cidrs: [10.20.0.0/16, fd12:3456::/48]
""",
    )

    policies = load_webhook_network_policies(tmp_path)

    assert tuple(str(item) for item in policies["receiver"].allowed_networks) == (
        "10.20.0.0/16",
        "fd12:3456::/48",
    )


@pytest.mark.parametrize(
    "content",
    [
        "schema_version: 1\npolicies: &shared {}\n",
        "schema_version: 1\npolicies: *shared\n",
        "schema_version: !!int '1'\npolicies: {}\n",
        "schema_version: 1\nschema_version: 1\npolicies: {}\n",
        "- not-a-mapping\n",
    ],
)
def test_loader_rejects_unsafe_or_ambiguous_yaml(tmp_path: Path, content: str) -> None:
    write_policy(tmp_path / ".ansiblectl/webhook-network-policies.yaml", content)

    with pytest.raises(ConfigurationError):
        load_webhook_network_policies(tmp_path)


def test_loader_rejects_symlinks_non_regular_and_oversized_files(tmp_path: Path) -> None:
    private = tmp_path / ".ansiblectl"
    private.mkdir()
    outside = tmp_path.parent / "outside-policy.yaml"
    outside.write_text("schema_version: 1\npolicies: {}\n", encoding="utf-8")
    path = private / "webhook-network-policies.yaml"
    path.symlink_to(outside)
    with pytest.raises(ConfigurationError, match="regular file"):
        load_webhook_network_policies(tmp_path)

    path.unlink()
    path.mkdir()
    with pytest.raises(ConfigurationError):
        load_webhook_network_policies(tmp_path)

    path.rmdir()
    path.write_bytes(b" " * (MAX_WEBHOOK_NETWORK_POLICY_BYTES + 1))
    with pytest.raises(ConfigurationError, match="bounded"):
        load_webhook_network_policies(tmp_path)


def test_loader_rejects_invalid_utf8_without_echoing_content(tmp_path: Path) -> None:
    path = tmp_path / ".ansiblectl/webhook-network-policies.yaml"
    path.parent.mkdir()
    path.write_bytes(b"schema_version: 1\npolicies: \xffsecret-detail")

    with pytest.raises(ConfigurationError) as caught:
        load_webhook_network_policies(tmp_path)

    assert "secret-detail" not in str(caught.value)
