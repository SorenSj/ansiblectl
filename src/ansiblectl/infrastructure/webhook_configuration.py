"""Workspace-scoped YAML configuration for outbound webhook endpoints."""

from pathlib import Path

import yaml

from ansiblectl.domain.errors import ConfigurationError
from ansiblectl.domain.webhook_network_policy import WebhookNetworkPolicy
from ansiblectl.domain.webhooks import WebhookEndpoint, parse_webhook_endpoints


def load_webhook_endpoints(
    workspace_root: Path,
    policies: dict[str, WebhookNetworkPolicy] | None = None,
) -> dict[str, WebhookEndpoint]:
    """Load the private workspace endpoint document, or return no endpoints."""

    root = workspace_root.resolve()
    path = root / ".ansiblectl" / "webhooks.yaml"
    if not path.is_file():
        return {}
    if not path.resolve().is_relative_to(root):
        raise ConfigurationError("Webhook configuration must remain inside the workspace.")
    try:
        values = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ConfigurationError("Webhook configuration could not be parsed safely.") from error
    if not isinstance(values, dict):
        raise ConfigurationError("Webhook configuration must be a YAML mapping.")
    return dict(parse_webhook_endpoints(values, str(path), policies))


__all__ = ["load_webhook_endpoints"]
