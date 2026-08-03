"""Subprocess-adapter tests."""

import stat
import subprocess
from pathlib import Path

import pytest

from ansiblectl.domain.execution import ExecutionRequest, ExecutionStatus
from ansiblectl.domain.playbook import PlaybookReference
from ansiblectl.infrastructure.local_execution import LocalExecutionAdapter


def test_adapter_passes_special_arguments_as_an_argument_vector(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess([], 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    request = ExecutionRequest(
        ("ansible-playbook", "name with spaces;$(nope)"), tmp_path, {"SAFE": "value"}
    )

    result = LocalExecutionAdapter().execute(request)

    assert result.status is ExecutionStatus.COMPLETED
    assert captured["args"] == (request.argv,)
    assert captured["kwargs"] == {
        "cwd": tmp_path,
        "env": {"SAFE": "value"},
        "capture_output": True,
        "check": False,
        "shell": False,
        "timeout": None,
        "text": True,
    }


def test_adapter_classifies_timeout_and_preserves_identifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def timed_out(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired("ansible-playbook", 1)

    monkeypatch.setattr(subprocess, "run", timed_out)
    request = ExecutionRequest(("ansible-playbook", "site.yml"), tmp_path, {}, timeout_seconds=1)

    result = LocalExecutionAdapter().execute(request)

    assert result.execution_id == request.execution_id
    assert result.status is ExecutionStatus.TIMED_OUT


def test_adapter_honors_pre_start_cancellation(tmp_path: Path) -> None:
    result = LocalExecutionAdapter().execute(
        ExecutionRequest(("ansible-playbook", "site.yml"), tmp_path, {}, cancel_requested=True)
    )

    assert result.status is ExecutionStatus.CANCELLED


def test_adapter_persists_non_empty_output_as_private_references(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def completed(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 2, stdout="play recap\n", stderr="failure\n")

    monkeypatch.setattr(subprocess, "run", completed)

    request = ExecutionRequest.for_playbook(
        ("ansible-playbook", "site.yml"),
        tmp_path,
        {},
        PlaybookReference(tmp_path / "site.yml", "main"),
        resolved_revision="abc123",
        inventory_digest="sha256:inventory",
        playbook_digest="sha256:playbook",
        verbosity=3,
        diff=True,
    )
    result = LocalExecutionAdapter().execute(request)

    assert result.status is ExecutionStatus.FAILED
    assert result.stdout_reference is not None
    assert result.stderr_reference is not None
    assert result.requested_revision == "main"
    assert result.resolved_revision == "abc123"
    assert result.inventory_digest == "sha256:inventory"
    assert result.playbook_digest == "sha256:playbook"
    assert result.playbook_path == "site.yml"
    assert result.verbosity == 3
    assert result.diff is True
    stdout_path = Path(result.stdout_reference)
    stderr_path = Path(result.stderr_reference)
    assert stdout_path.read_text(encoding="utf-8") == "play recap\n"
    assert stderr_path.read_text(encoding="utf-8") == "failure\n"
    assert stat.S_IMODE(stdout_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(stderr_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(stdout_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(stdout_path.parent.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(stdout_path.parent.parent.parent.stat().st_mode) == 0o700
    assert request_identifier_is_not_a_path_component(stdout_path, result.execution_id)


def request_identifier_is_not_a_path_component(path: Path, execution_id: str) -> bool:
    return execution_id not in path.parts


def test_adapter_persists_partial_timeout_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def timed_out(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(
            "ansible-playbook", 1, output=b"partial stdout\n", stderr=b"partial stderr\n"
        )

    monkeypatch.setattr(subprocess, "run", timed_out)

    result = LocalExecutionAdapter().execute(
        ExecutionRequest(("ansible-playbook", "site.yml"), tmp_path, {}, timeout_seconds=1)
    )

    assert result.status is ExecutionStatus.TIMED_OUT
    assert result.stdout_reference is not None
    assert result.stderr_reference is not None
    assert Path(result.stdout_reference).read_text(encoding="utf-8") == "partial stdout\n"
    assert Path(result.stderr_reference).read_text(encoding="utf-8") == "partial stderr\n"


def test_adapter_omits_references_for_empty_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def completed(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", completed)

    result = LocalExecutionAdapter().execute(
        ExecutionRequest(("ansible-playbook", "site.yml"), tmp_path, {})
    )

    assert result.stdout_reference is None
    assert result.stderr_reference is None
