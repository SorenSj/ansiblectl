"""Prepared Ansible playbook execution use case."""

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path

from ansiblectl.application.execution import ExecutionService, GovernedExecutionResult
from ansiblectl.application.inventory import InventoryService
from ansiblectl.application.policy import PolicyService
from ansiblectl.domain.execution import ExecutionRequest
from ansiblectl.domain.playbook import select_playbook
from ansiblectl.domain.policy import EnforcementMode, EvaluationRequest

InventoryMaterializer = Callable[[Mapping[str, object]], AbstractContextManager[Path]]


@dataclass(frozen=True)
class RunService:
    inventory: InventoryService
    execution: ExecutionService
    policy: PolicyService
    materialize_inventory: InventoryMaterializer

    def run_check(
        self,
        workspace_root: Path,
        playbook_identifier: Path,
        revision: str,
        environment: Mapping[str, str],
        timeout_seconds: float,
        policy_mode: EnforcementMode,
    ) -> GovernedExecutionResult:
        """Validate inputs and execute ansible-playbook with an ephemeral canonical inventory."""

        selected = select_playbook(workspace_root, playbook_identifier, revision)
        resolved_inventory = self.inventory.resolve()
        report = self.policy.evaluate(
            EvaluationRequest("run.check", str(selected.path)), policy_mode
        )
        if not report.allowed:
            return GovernedExecutionResult(report, None)
        with self.materialize_inventory(resolved_inventory.canonical()) as inventory_path:
            request = ExecutionRequest.for_playbook(
                (
                    "ansible-playbook",
                    "--inventory",
                    str(inventory_path),
                    "--check",
                    str(selected.path),
                ),
                workspace_root.resolve(),
                environment,
                selected,
                timeout_seconds,
            )
            return GovernedExecutionResult(report, self.execution.execute(request))
