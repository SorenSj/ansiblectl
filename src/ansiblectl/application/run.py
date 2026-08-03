"""Prepared Ansible playbook execution use case."""

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path

from ansiblectl.application.execution import ExecutionService, GovernedExecutionResult
from ansiblectl.application.inventory import InventoryService
from ansiblectl.application.policy import PolicyService
from ansiblectl.application.repository import RepositoryService
from ansiblectl.domain.errors import ExecutionError
from ansiblectl.domain.execution import ExecutionMode, ExecutionRequest, ExecutionTargeting
from ansiblectl.domain.inventory import canonical_inventory_digest
from ansiblectl.domain.playbook import playbook_digest, select_playbook
from ansiblectl.domain.policy import EnforcementMode, EvaluationRequest
from ansiblectl.domain.repository import RepositoryRequest

InventoryMaterializer = Callable[[Mapping[str, object]], AbstractContextManager[Path]]


@dataclass(frozen=True)
class RunService:
    inventory: InventoryService
    execution: ExecutionService
    policy: PolicyService
    materialize_inventory: InventoryMaterializer
    repository: RepositoryService | None = None

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
        selected_playbook_digest = playbook_digest(selected)
        resolved_inventory = self.inventory.resolve()
        canonical_inventory = resolved_inventory.canonical()
        inventory_digest = canonical_inventory_digest(canonical_inventory)
        repository = (
            None
            if self.repository is None
            else self.repository.inspect_for_execution(
                RepositoryRequest(workspace_root.resolve(), workspace_root.resolve(), revision)
            )
        )
        report = self.policy.evaluate(
            EvaluationRequest(
                f"run.{mode.value}",
                str(selected.path),
                {
                    "limit": targeting.limit,
                    "tags": targeting.tags,
                    "skip_tags": targeting.skip_tags,
                    "repository_dirty": None if repository is None else repository.dirty,
                    "resolved_revision": (
                        None if repository is None else repository.resolved_revision
                    ),
                    "inventory_digest": inventory_digest,
                    "playbook_digest": selected_playbook_digest,
                },
            ),
            policy_mode,
        )
        if not report.allowed:
            return GovernedExecutionResult(report, None)
        with self.materialize_inventory(canonical_inventory) as inventory_path:
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
                None if repository is None else repository.resolved_revision,
                inventory_digest,
                selected_playbook_digest,
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
