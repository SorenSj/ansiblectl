"""Built-in policy tests."""

from ansiblectl.application.standard_policies import ApplyRequiresLimitPolicy
from ansiblectl.domain.policy import EvaluationRequest


def test_apply_requires_explicit_limit_with_stable_finding() -> None:
    policy = ApplyRequiresLimitPolicy()

    findings = policy.evaluate(EvaluationRequest("run.apply", "site.yml", {"limit": None}))

    assert len(findings) == 1
    assert findings[0].rule_id == "ANSIBLECTL-APPLY-001"
    assert findings[0].severity == "high"
    assert "--limit" in (findings[0].remediation or "")


def test_apply_with_limit_and_check_mode_have_no_finding() -> None:
    policy = ApplyRequiresLimitPolicy()

    assert policy.evaluate(EvaluationRequest("run.apply", "site.yml", {"limit": "web"})) == ()
    assert policy.evaluate(EvaluationRequest("run.check", "site.yml", {"limit": None})) == ()
