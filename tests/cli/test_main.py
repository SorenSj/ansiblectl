"""CLI contract tests."""

from io import StringIO

import pytest

from ansiblectl.application.status import Status
from ansiblectl.cli.main import EXIT_INVALID_INPUT, EXIT_SUCCESS, main


class FakeStatusService:
    def get_status(self) -> Status:
        return Status(version="9.9.9", message="Fake service is ready.")


def test_status_uses_injected_application_service() -> None:
    output = StringIO()

    result = main(
        ["--output-format", "json", "status"], status_service=FakeStatusService(), stdout=output
    )

    assert result == EXIT_SUCCESS
    assert output.getvalue() == '{"message": "Fake service is ready.", "version": "9.9.9"}\n'


def test_help_lists_global_options_and_status_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--help"])

    captured = capsys.readouterr()
    assert raised.value.code == EXIT_SUCCESS
    assert "--workspace" in captured.out
    assert "--output-format" in captured.out
    assert "status" in captured.out


def test_invalid_argument_uses_documented_invalid_input_exit_code(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--unknown"])

    captured = capsys.readouterr()
    assert raised.value.code == EXIT_INVALID_INPUT
    assert "error:" in captured.err
