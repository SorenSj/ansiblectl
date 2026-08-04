"""Safe workspace loading for named webhook private-network policies."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import yaml
from yaml.tokens import AliasToken, AnchorToken, TagToken

from ansiblectl.domain.errors import ConfigurationError
from ansiblectl.domain.webhook_network_policy import (
    WebhookNetworkPolicy,
    parse_webhook_network_policies,
)

MAX_WEBHOOK_NETWORK_POLICY_BYTES = 65_536


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[object, object]:
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as error:
            raise yaml.constructor.ConstructorError("mapping key is not scalar") from error
        if duplicate:
            raise yaml.constructor.ConstructorError("duplicate mapping key")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def load_webhook_network_policies(workspace_root: Path) -> dict[str, WebhookNetworkPolicy]:
    """Load the optional private policy document without following filesystem links."""

    root = workspace_root.resolve()
    private = root / ".ansiblectl"
    path = private / "webhook-network-policies.yaml"
    if private.is_symlink() or path.is_symlink():
        raise ConfigurationError("Webhook network policy configuration must be a regular file.")
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    except FileNotFoundError:
        return {}
    except OSError as error:
        raise ConfigurationError(
            "Webhook network policy configuration could not be read safely."
        ) from error
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size > MAX_WEBHOOK_NETWORK_POLICY_BYTES
        ):
            raise ConfigurationError("Webhook network policy configuration must be a bounded file.")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            encoded = handle.read(MAX_WEBHOOK_NETWORK_POLICY_BYTES + 1)
    except OSError as error:
        raise ConfigurationError(
            "Webhook network policy configuration could not be read safely."
        ) from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(encoded) > MAX_WEBHOOK_NETWORK_POLICY_BYTES:
        raise ConfigurationError("Webhook network policy configuration must be a bounded file.")
    try:
        text = encoded.decode("utf-8")
        if any(isinstance(token, (AliasToken, AnchorToken, TagToken)) for token in yaml.scan(text)):
            raise ConfigurationError("Webhook network policy YAML uses forbidden syntax.")
        values = yaml.load(text, Loader=_UniqueKeyLoader)
    except (UnicodeDecodeError, yaml.YAMLError) as error:
        raise ConfigurationError(
            "Webhook network policy configuration could not be parsed safely."
        ) from error
    if not isinstance(values, dict):
        raise ConfigurationError("Webhook network policy configuration must be a YAML mapping.")
    return dict(parse_webhook_network_policies(values, "workspace policy configuration"))


__all__ = ["MAX_WEBHOOK_NETWORK_POLICY_BYTES", "load_webhook_network_policies"]
