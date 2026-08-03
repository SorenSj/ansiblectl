"""Prepared Ansible playbook execution use case."""

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path

from ansiblectl.application.execution import ExecutionService, GovernedExecutionResult
from ansiblectl.application.inventory import InventoryService
from ansiblectl.application.policy import PolicyService
from ansiblectl.domain.errors import ExecutionError
from ansiblectl.domain.execution import ExecutionMode, ExecutionRequest, ExecutionTargeting
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
        targeting: ExecutionTargeting | None = None,
    ) -> GovernedExecutionResult:
        """Validate inputs and execute ansible-playbook with an ephemeral canonical inventory."""

        return self._run(
            workspace_root,
            playbook_identifier,
            revision,
            environment,
            timeout_seconds,
            policy_mode,
            targeting or ExecutionTargeting(),
            ExecutionMode.CHECK,
        )

    def run_apply(
        self,
        workspace_root: Path,
        playbook_identifier: Path,
        revision: str,
        environment: Mapping[str, str],
        timeout_seconds: float,
        policy_mode: EnforcementMode,
        confirmed: bool,
        targeting: ExecutionTargeting | None = None,
    ) -> GovernedExecutionResult:
        """Execute an explicitly confirmed, policy-governed Ansible apply."""

        if not confirmed:
            raise ExecutionError("Apply mode requires explicit confirmation.")
        return self._run(
            workspace_root,
            playbook_identifier,
            revision,
            environment,
            timeout_seconds,
            policy_mode,
            targeting or ExecutionTargeting(),
            ExecutionMode.APPLY,
        )

    def _run(
        self,
        workspace_root: Path,
        playbook_identifier: Path,
        revision: str,
        environment: Mapping[str, str],
        timeout_seconds: float,
        policy_mode: EnforcementMode,
        targeting: ExecutionTargeting,
        mode: ExecutionMode,
    ) -> GovernedExecutionResult:

        selected = select_playbook(workspace_root, playbook_identifier, revision)
        resolved_inventory = self.inventory.resolve()
        report = self.policy.evaluate(
            EvaluationRequest(f"run.{mode.value}", str(selected.path)), policy_mode
        )
        if not report.allowed:
            return GovernedExecutionResult(report, None)
        with self.materialize_inventory(resolved_inventory.canonical()) as inventory_path:
            request = ExecutionRequest.for_playbook(
                (
                    "ansible-playbook",
                    "--inventory",
                    str(inventory_path),
                    *(("--check",) if mode is ExecutionMode.CHECK else ()),
                    *_targeting_arguments(targeting),
                    str(selected.path),
                ),
                workspace_root.resolve(),
                environment,
                selected,
                timeout_seconds,
                targeting,
                mode,
            )
            return GovernedExecutionResult(report, self.execution.execute(request))


def _targeting_arguments(targeting: ExecutionTargeting) -> tuple[str, ...]:
    arguments: list[str] = []
    if targeting.limit is not None:
        arguments.extend(("--limit", targeting.limit))
    if targeting.tags:
        arguments.extend(("--tags", ",".join(targeting.tags)))
    if targeting.skip_tags:
        arguments.extend(("--skip-tags", ",".join(targeting.skip_tags)))
    return tuple(arguments)
