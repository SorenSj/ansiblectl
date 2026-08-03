"""Configuration model tests."""

import pytest

from ansiblectl.domain.configuration import ConfigurationSource, make_effective_configuration
from ansiblectl.domain.errors import ConfigurationError


def test_higher_precedence_value_wins_and_secrets_are_redacted() -> None:
    configuration = make_effective_configuration(
        [
            ConfigurationSource(
                "user",
                {"schema_version": 1, "log_level": "warning", "secrets": {"token": "env:TOKEN"}},
            ),
            ConfigurationSource("project", {"schema_version": 1, "log_level": "debug"}),
        ]
    )
    assert configuration.log_level == "debug"
    assert configuration.provenance["log_level"] == "project"
    assert configuration.redacted()["secrets"] == {"token": "<redacted>"}
    assert "TOKEN" not in str(configuration.redacted())


def test_invalid_field_has_source_and_safe_correction() -> None:
    with pytest.raises(ConfigurationError, match="Unknown field 'oops' in workspace. Remove"):
        make_effective_configuration(
            [ConfigurationSource("workspace", {"schema_version": 1, "oops": True})]
        )
