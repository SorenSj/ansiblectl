"""Policy engine tests."""

from dataclasses import dataclass

from ansiblectl.domain.policy import EnforcementMode, EvaluationRequest, PolicyFinding, evaluate


@dataclass(frozen=True)
class FakePolicy:
    finding: PolicyFinding

    def evaluate(self, request: EvaluationRequest) -> tuple[PolicyFinding, ...]:
        return (self.finding,)


def test_deny_is_deterministic_and_blocks_before_execution() -> None:
    first = FakePolicy(PolicyFinding("B", "high", "second", "playbook.yml", "Fix it."))
    second = FakePolicy(PolicyFinding("A", "high", "first", "playbook.yml"))
    request = EvaluationRequest("execute", "playbook.yml")

    report = evaluate([first, second], request, EnforcementMode.DENY)

    assert [finding.rule_id for finding in report.findings] == ["A", "B"]
    assert report.allowed is False
    assert evaluate([first, second], request, EnforcementMode.DENY) == report

    assert report.machine_output() == {
        "schema_version": 1,
        "mode": "deny",
        "allowed": False,
        "findings": [
            {
                "rule_id": "A",
                "severity": "high",
                "message": "first",
                "location": "playbook.yml",
                "remediation": None,
            },
            {
                "rule_id": "B",
                "severity": "high",
                "message": "second",
                "location": "playbook.yml",
                "remediation": "Fix it.",
            },
        ],
    }
