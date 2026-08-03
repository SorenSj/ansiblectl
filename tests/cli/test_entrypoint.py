"""Installed CLI failure-boundary tests."""

import json
from io import StringIO

import pytest

from ansiblectl.cli.main import EXIT_UNEXPECTED_FAILURE, cli


@pytest.mark.parametrize(
    ("format_arguments", "output_format"),
    [
        ([], "human"),
        (["--output-format", "json"], "json"),
        (["--output-format=json"], "json"),
    ],
)
def test_entrypoint_maps_unexpected_failure_without_exposing_exception(
    monkeypatch: pytest.MonkeyPatch,
    format_arguments: list[str],
    output_format: str,
) -> None:
    stdout, stderr = StringIO(), StringIO()

    def fail(*args: object, **kwargs: object) -> int:
        raise RuntimeError("sensitive adapter detail")

    monkeypatch.setattr("ansiblectl.cli.main.main", fail)

    result = cli([*format_arguments, "status"], stdout=stdout, stderr=stderr)

    assert result == EXIT_UNEXPECTED_FAILURE
    assert "sensitive adapter detail" not in stdout.getvalue() + stderr.getvalue()
    if output_format == "json":
        assert stderr.getvalue() == ""
        assert json.loads(stdout.getvalue()) == {
            "kind": "unexpected_failure",
            "operation": "ansiblectl",
            "reason": "Unexpected internal failure.",
            "remediation": "Retry with increased verbosity and report the failure.",
        }
    else:
        assert stdout.getvalue() == ""
        assert "Unexpected internal failure" in stderr.getvalue()


def test_entrypoint_does_not_intercept_keyboard_interrupt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def interrupt(*args: object, **kwargs: object) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr("ansiblectl.cli.main.main", interrupt)

    with pytest.raises(KeyboardInterrupt):
        cli(["status"], stdout=StringIO(), stderr=StringIO())
