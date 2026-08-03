"""Deterministic built-in policies for high-risk execution operations."""

from dataclasses import dataclass

from ansiblectl.domain.policy import EvaluationRequest, PolicyFinding


@dataclass(frozen=True)
class ApplyRequiresLimitPolicy:
    """Require an explicit Ansible host limit for apply-mode execution."""

    def evaluate(self, request: EvaluationRequest) -> tuple[PolicyFinding, ...]:
        if request.operation != "run.apply" or request.attributes.get("limit") is not None:
            return ()
        return (
            PolicyFinding(
                "ANSIBLECTL-APPLY-001",
                "high",
                "Apply mode requires an explicit Ansible host limit.",
                request.location,
                "Retry with --limit set to the intended host or group pattern.",
            ),
        )


@dataclass(frozen=True)
class ApplyRequiresCleanRepositoryPolicy:
    """Prevent apply from using uncommitted workspace content."""

    def evaluate(self, request: EvaluationRequest) -> tuple[PolicyFinding, ...]:
        if (
            request.operation != "run.apply"
            or request.attributes.get("repository_dirty") is not True
        ):
            return ()
        return (
            PolicyFinding(
                "ANSIBLECTL-APPLY-002",
                "high",
                "Apply mode requires a clean repository worktree.",
                request.location,
                "Commit or stash workspace changes before applying the playbook.",
            ),
        )
