"""Prepared Ansible playbook execution use case."""

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path

from ansiblectl.application.configuration import ConfigurationService
from ansiblectl.application.execution import ExecutionService, GovernedExecutionResult
from ansiblectl.application.inventory import InventoryService
from ansiblectl.application.policy import PolicyService
from ansiblectl.application.repository import RepositoryService
from ansiblectl.domain.errors import ExecutionError
from ansiblectl.domain.execution import ExecutionMode, ExecutionRequest, ExecutionTargeting
from ansiblectl.domain.inventory import canonical_inventory_digest
from ansiblectl.domain.playbook import PlaybookReference, playbook_digest, select_playbook
from ansiblectl.domain.policy import EnforcementMode, EvaluationRequest, PolicyReport
from ansiblectl.domain.repository import RepositoryRequest

InventoryMaterializer = Callable[[Mapping[str, object]], AbstractContextManager[Path]]
ExecutionEnvironment = Mapping[str, str] | Callable[[], Mapping[str, str]]


@dataclass(frozen=True)
class RunPreflightResult:
    """Safe evidence produced before inventory materialization or execution."""

    report: PolicyReport
    mode: ExecutionMode
    playbook_path: str
    requested_revision: str
    resolved_revision: str | None
    inventory_digest: str
    playbook_digest: str
    targeting: ExecutionTargeting
    verbosity: int
    diff: bool


@dataclass(frozen=True)
class _PreparedRun:
    result: RunPreflightResult
    selected: PlaybookReference
    canonical_inventory: Mapping[str, object]


@dataclass(frozen=True)
class RunService:
    inventory: InventoryService
    execution: ExecutionService
    policy: PolicyService
    materialize_inventory: InventoryMaterializer
    repository: RepositoryService | None = None
    configuration: ConfigurationService | None = None

    def preflight(
        self,
        workspace_root: Path,
        playbook_identifier: Path,
        revision: str,
        policy_mode: EnforcementMode,
        mode: ExecutionMode,
        targeting: ExecutionTargeting | None = None,
        verbosity: int = 0,
        diff: bool = False,
    ) -> RunPreflightResult:
        """Validate all run inputs and policies without materializing or executing."""

        return self._prepare(
            workspace_root,
            playbook_identifier,
            revision,
            policy_mode,
            targeting or ExecutionTargeting(),
            mode,
            verbosity,
            diff,
        ).result

    def run_check(
        self,
        workspace_root: Path,
        playbook_identifier: Path,
        revision: str,
        environment: ExecutionEnvironment,
        timeout_seconds: float,
        policy_mode: EnforcementMode,
        targeting: ExecutionTargeting | None = None,
        verbosity: int = 0,
        diff: bool = False,
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
            verbosity,
            diff,
        )

    def run_apply(
        self,
        workspace_root: Path,
        playbook_identifier: Path,
        revision: str,
        environment: ExecutionEnvironment,
        timeout_seconds: float,
        policy_mode: EnforcementMode,
        confirmed: bool,
        targeting: ExecutionTargeting | None = None,
        verbosity: int = 0,
        diff: bool = False,
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
            verbosity,
            diff,
        )

    def _run(
        self,
        workspace_root: Path,
        playbook_identifier: Path,
        revision: str,
        environment: ExecutionEnvironment,
        timeout_seconds: float,
        policy_mode: EnforcementMode,
        targeting: ExecutionTargeting,
        mode: ExecutionMode,
        verbosity: int,
        diff: bool,
    ) -> GovernedExecutionResult:
        verbosity_arguments = _verbosity_arguments(verbosity)
        prepared = self._prepare(
            workspace_root,
            playbook_identifier,
            revision,
            policy_mode,
            targeting,
            mode,
            verbosity,
            diff,
        )
        result = prepared.result
        if not result.report.allowed:
            return GovernedExecutionResult(result.report, None)
        resolved_environment = environment() if callable(environment) else environment
        with self.materialize_inventory(prepared.canonical_inventory) as inventory_path:
            request = ExecutionRequest.for_playbook(
                (
                    "ansible-playbook",
                    *verbosity_arguments,
                    "--inventory",
                    str(inventory_path),
                    *(("--check",) if mode is ExecutionMode.CHECK else ()),
                    *(("--diff",) if diff else ()),
                    *_targeting_arguments(targeting),
                    str(prepared.selected.path),
                ),
                workspace_root.resolve(),
                resolved_environment,
                prepared.selected,
                timeout_seconds,
                targeting,
                mode,
                result.resolved_revision,
                result.inventory_digest,
                result.playbook_digest,
                verbosity,
                diff,
            )
            return GovernedExecutionResult(result.report, self.execution.execute(request))

    def _prepare(
        self,
        workspace_root: Path,
        playbook_identifier: Path,
        revision: str,
        policy_mode: EnforcementMode,
        targeting: ExecutionTargeting,
        mode: ExecutionMode,
        verbosity: int,
        diff: bool,
    ) -> _PreparedRun:
        _verbosity_arguments(verbosity)
        if self.configuration is not None:
            self.configuration.resolve()
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
                    "verbosity": verbosity,
                    "diff": diff,
                },
            ),
            policy_mode,
        )
        result = RunPreflightResult(
            report,
            mode,
            selected.path.relative_to(workspace_root.resolve()).as_posix(),
            revision,
            None if repository is None else repository.resolved_revision,
            inventory_digest,
            selected_playbook_digest,
            targeting,
            verbosity,
            diff,
        )
        return _PreparedRun(result, selected, canonical_inventory)


def _targeting_arguments(targeting: ExecutionTargeting) -> tuple[str, ...]:
    arguments: list[str] = []
    if targeting.limit is not None:
        arguments.extend(("--limit", targeting.limit))
    if targeting.tags:
        arguments.extend(("--tags", ",".join(targeting.tags)))
    if targeting.skip_tags:
        arguments.extend(("--skip-tags", ",".join(targeting.skip_tags)))
    return tuple(arguments)


def _verbosity_arguments(verbosity: int) -> tuple[str, ...]:
    if verbosity < 0:
        raise ExecutionError("Execution verbosity must be zero or greater.")
    return () if verbosity == 0 else (f"-{'v' * verbosity}",)
