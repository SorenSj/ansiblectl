"""Compatibility tests for the public command-envelope import surface."""

import ansiblectl.envelopes as public_envelopes
from ansiblectl.domain import envelopes as domain_envelopes


def test_public_envelope_module_exports_the_documented_contract() -> None:
    assert set(public_envelopes.__all__) == {
        "ENVELOPE_SCHEMA_VERSION",
        "ErrorEnvelope",
        "StructuredError",
        "SuccessEnvelope",
    }
    for name in public_envelopes.__all__:
        assert getattr(public_envelopes, name) is getattr(domain_envelopes, name)
