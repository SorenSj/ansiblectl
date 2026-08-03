"""Public versioned command-envelope contracts for ansiblectl integrations."""

from ansiblectl.domain.envelopes import (
    ENVELOPE_SCHEMA_VERSION,
    ErrorEnvelope,
    StructuredError,
    SuccessEnvelope,
)

__all__ = [
    "ENVELOPE_SCHEMA_VERSION",
    "ErrorEnvelope",
    "StructuredError",
    "SuccessEnvelope",
]
