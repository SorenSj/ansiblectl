"""Subprocess-adapter tests."""

import subprocess
from pathlib import Path

import pytest

from ansiblectl.domain.execution import ExecutionRequest, ExecutionStatus
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
