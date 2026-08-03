"""Compatibility tests for the public command-result import surface."""

import ansiblectl.results as public_results
from ansiblectl.domain.results import CommandResult, CommandWarning


def test_public_result_module_exports_the_documented_contract() -> None:
    assert public_results.__all__ == ["CommandResult", "CommandWarning"]
    assert public_results.CommandResult is CommandResult
    assert public_results.CommandWarning is CommandWarning
