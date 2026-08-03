"""Contract tests binding envelope models to the published JSON Schema."""

import json
from pathlib import Path

from ansiblectl.domain.context import CommandContext
from ansiblectl.domain.envelopes import ErrorEnvelope, SuccessEnvelope
from ansiblectl.domain.errors import ConflictError
from ansiblectl.domain.results import CommandResult

SCHEMA_PATH = Path("docs/schemas/command-envelope-v1.schema.json")
_OPERATION_ID = "00000000Z80000000000000000"


def test_published_schema_tracks_required_model_fields_and_discriminators() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    definitions = schema["$defs"]
    base_required = set(definitions["baseEnvelope"]["required"])

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert base_required == {
        "schema_version",
        "status",
        "operation_id",
        "command",
        "changed",
        "warnings",
        "metadata",
    }
    assert definitions["successEnvelope"]["allOf"][1]["required"] == ["message", "data"]
    assert definitions["errorEnvelope"]["allOf"][1]["required"] == ["error"]


def test_model_payloads_match_schema_discriminator_and_required_keys() -> None:
    context = CommandContext(_OPERATION_ID, "repository sync", False, "json", False)
    success = SuccessEnvelope.from_result(context, CommandResult(data={"revision": "main"}))
    failure = ErrorEnvelope.from_error(context, ConflictError("Conflict."))
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    required = set(schema["$defs"]["baseEnvelope"]["required"])

    success_payload = success.to_payload()
    error_payload = failure.to_payload()
    assert required <= success_payload.keys()
    assert required <= error_payload.keys()
    assert success_payload["status"] == "success"
    assert {"message", "data"} <= success_payload.keys()
    assert error_payload["status"] == "error"
    assert error_payload["changed"] is False
    assert "error" in error_payload
