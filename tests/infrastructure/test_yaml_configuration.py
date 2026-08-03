"""Safe YAML source-provider tests."""

from pathlib import Path

import pytest

from ansiblectl.domain.errors import ConfigurationError
from ansiblectl.domain.workspace import Workspace
from ansiblectl.infrastructure.yaml_configuration import LocalConfigurationSourceProvider


def _workspace(root: Path) -> Workspace:
    return Workspace(root=root, metadata_path=root / ".ansiblectl/workspace.json", schema_version=1)


def test_provider_loads_workspace_project_and_environment_in_precedence_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home)
    (home / ".config/ansiblectl").mkdir(parents=True)
    (home / ".config/ansiblectl/config.yaml").write_text("schema_version: 1\nlog_level: warning\n")
    (tmp_path / ".ansiblectl").mkdir()
    (tmp_path / ".ansiblectl/config.yaml").write_text("schema_version: 1\nlog_level: info\n")
    (tmp_path / "ansiblectl.yaml").write_text("schema_version: 1\nproject_name: demo\n")

    sources = LocalConfigurationSourceProvider(
        _workspace(tmp_path), {"ANSIBLECTL_LOG_LEVEL": "debug"}
    ).sources()

    assert [source.origin for source in sources] == [
        "built-in defaults",
        str(home / ".config/ansiblectl/config.yaml"),
        str(tmp_path / ".ansiblectl/config.yaml"),
        str(tmp_path / "ansiblectl.yaml"),
        "environment:ANSIBLECTL_LOG_LEVEL",
    ]


def test_provider_rejects_unsafe_or_non_mapping_yaml(tmp_path: Path) -> None:
    (tmp_path / ".ansiblectl").mkdir()
    (tmp_path / ".ansiblectl/config.yaml").write_text("- invalid\n")

    with pytest.raises(ConfigurationError, match="must be a YAML mapping"):
        LocalConfigurationSourceProvider(_workspace(tmp_path), {}).sources()
