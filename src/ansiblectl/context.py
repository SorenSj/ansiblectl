"""Public command-context contracts for ansiblectl integrations."""

from ansiblectl.domain.context import CommandContext, create_command_context, new_operation_id

__all__ = ["CommandContext", "create_command_context", "new_operation_id"]
