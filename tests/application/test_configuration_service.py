"""Configuration use-case tests."""

from dataclasses import dataclass

from ansiblectl.application.configuration import ConfigurationService
from ansiblectl.domain.configuration import ConfigurationSource


@dataclass(frozen=True)
class FakeSourceProvider:
    def sources(self) -> list[ConfigurationSource]:
        return [ConfigurationSource("fake", {"schema_version": 1, "project_name": "demo"})]


def test_resolve_uses_the_explicit_source_provider() -> None:
    assert ConfigurationService(FakeSourceProvider()).resolve().project_name == "demo"
