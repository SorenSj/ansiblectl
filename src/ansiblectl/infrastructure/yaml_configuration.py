"""Safe YAML configuration sources for the local runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from ansiblectl.domain.configuration import CONFIGURATION_SCHEMA_VERSION, ConfigurationSource
from ansiblectl.domain.errors import ConfigurationError
from ansiblectl.domain.workspace import Workspace


@dataclass(frozen=True)
class LocalConfigurationSourceProvider:
    """Load documented sources in ADR-0008 precedence order."""

    workspace: Workspace
    environment: dict[str, str]

    def sources(self) -> list[ConfigurationSource]:
        sources = [
            ConfigurationSource(
                "built-in defaults", {"schema_version": CONFIGURATION_SCHEMA_VERSION}
            )
        ]
        sources.extend(_load_optional(Path.home() / ".config/ansiblectl/config.yaml"))
        sources.extend(_load_optional(self.workspace.root / ".ansiblectl/config.yaml"))
        sources.extend(_load_optional(self.workspace.root / "ansiblectl.yaml"))
        if "ANSIBLECTL_LOG_LEVEL" in self.environment:
            sources.append(
                ConfigurationSource(
                    "environment:ANSIBLECTL_LOG_LEVEL",
                    {
                        "schema_version": CONFIGURATION_SCHEMA_VERSION,
                        "log_level": self.environment["ANSIBLECTL_LOG_LEVEL"],
                    },
                )
            )
        return sources


def _load_optional(path: Path) -> list[ConfigurationSource]:
    if not path.is_file():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ConfigurationError(
            f"Configuration at '{path}' cannot be parsed safely. Correct the YAML and retry."
        ) from error
    if not isinstance(data, dict):
        raise ConfigurationError(f"Configuration at '{path}' must be a YAML mapping.")
    return [ConfigurationSource(str(path), data)]
