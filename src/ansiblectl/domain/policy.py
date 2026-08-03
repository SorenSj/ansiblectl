"""Deterministic policy evaluation and enforcement."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class EnforcementMode(StrEnum):
    REPORT = "report"
    WARN = "warn"
    DENY = "deny"


@dataclass(frozen=True)
class EvaluationRequest:
    operation: str
    location: str


@dataclass(frozen=True)
class PolicyFinding:
    rule_id: str
    severity: str
    message: str
    location: str
    remediation: str | None = None


class Policy(Protocol):
    def evaluate(self, request: EvaluationRequest) -> tuple[PolicyFinding, ...]: ...


@dataclass(frozen=True)
class PolicyReport:
    findings: tuple[PolicyFinding, ...]
    mode: EnforcementMode

    @property
    def allowed(self) -> bool:
        return not (self.mode is EnforcementMode.DENY and self.findings)

    def machine_output(self) -> dict[str, object]:
        """Return the versioned public policy-report representation."""

        return {
            "schema_version": 1,
            "mode": self.mode.value,
            "allowed": self.allowed,
            "findings": [
                {
                    "rule_id": finding.rule_id,
                    "severity": finding.severity,
                    "message": finding.message,
                    "location": finding.location,
                    "remediation": finding.remediation,
                }
                for finding in self.findings
            ],
        }


def evaluate(
    policies: list[Policy], request: EvaluationRequest, mode: EnforcementMode
) -> PolicyReport:
    findings = tuple(finding for policy in policies for finding in policy.evaluate(request))
    return PolicyReport(
        tuple(sorted(findings, key=lambda finding: (finding.rule_id, finding.location))), mode
    )
