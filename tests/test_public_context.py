"""Compatibility tests for the public command-context import surface."""

import ansiblectl.context as public_context
from ansiblectl.domain.context import CommandContext, create_command_context, new_operation_id


def test_public_context_module_exports_the_documented_contract() -> None:
    assert public_context.__all__ == [
        "CommandContext",
        "create_command_context",
        "new_operation_id",
    ]
    assert public_context.CommandContext is CommandContext
    assert public_context.create_command_context is create_command_context
    assert public_context.new_operation_id is new_operation_id
