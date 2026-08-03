"""Configuration-resolution use case."""

from dataclasses import dataclass

from ansiblectl.domain.configuration import (
    ConfigurationSourceProvider,
    EffectiveConfiguration,
    make_effective_configuration,
)


@dataclass(frozen=True)
class ConfigurationService:
    """Resolve typed configuration through a source provider."""

    source_provider: ConfigurationSourceProvider

    def resolve(self) -> EffectiveConfiguration:
        """Return validated effective configuration and safe provenance."""

        return make_effective_configuration(self.source_provider.sources())
