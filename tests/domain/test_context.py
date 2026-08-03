"""Unit tests for command contexts and operation identifiers."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError

import pytest

from ansiblectl.domain.context import (
    CommandContext,
    _encode_ulid,
    _OperationIdGenerator,
    create_command_context,
    new_operation_id,
)
from ansiblectl.domain.errors import ValidationError


def test_ulid_encoding_is_canonical_and_preserves_sort_order() -> None:
    first = _encode_ulid(1_000, 0)
    second = _encode_ulid(1_001, 0)

    assert first == "00000000Z80000000000000000"
    assert len(first) == 26
    assert first < second


@pytest.mark.parametrize(
    ("timestamp", "randomness"),
    [(-1, 0), (1 << 48, 0), (0, -1), (0, 1 << 80)],
)
def test_ulid_encoding_rejects_values_outside_the_standard_width(
    timestamp: int, randomness: int
) -> None:
    with pytest.raises(ValueError):
        _encode_ulid(timestamp, randomness)


def test_new_operation_ids_are_canonical_and_unique() -> None:
    operation_ids = {new_operation_id() for _ in range(100)}

    assert len(operation_ids) == 100
    assert all(len(operation_id) == 26 for operation_id in operation_ids)
    assert all(operation_id[0] in "01234567" for operation_id in operation_ids)


def test_operation_ids_are_monotonic_within_one_millisecond(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("ansiblectl.domain.context.time.time_ns", lambda: 1_000_000_000)
    monkeypatch.setattr("ansiblectl.domain.context.secrets.randbits", lambda bits: 7)
    generator = _OperationIdGenerator()

    operation_ids = [generator.new() for _ in range(100)]

    assert operation_ids == sorted(operation_ids)
    assert len(set(operation_ids)) == 100


def test_operation_ids_remain_monotonic_when_wall_clock_moves_backwards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timestamps = iter((2_000_000_000, 1_000_000_000))
    monkeypatch.setattr("ansiblectl.domain.context.time.time_ns", lambda: next(timestamps))
    monkeypatch.setattr("ansiblectl.domain.context.secrets.randbits", lambda bits: 11)
    generator = _OperationIdGenerator()

    first = generator.new()
    second = generator.new()

    assert first < second


def test_operation_ids_remain_unique_across_concurrent_callers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("ansiblectl.domain.context.time.time_ns", lambda: 1_000_000_000)
    monkeypatch.setattr("ansiblectl.domain.context.secrets.randbits", lambda bits: 17)
    generator = _OperationIdGenerator()

    with ThreadPoolExecutor(max_workers=8) as executor:
        operation_ids = list(executor.map(lambda _: generator.new(), range(500)))

    assert len(set(operation_ids)) == 500


def test_operation_id_generator_reseeds_after_process_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process_ids = iter((100, 100, 200))
    randomness = iter((7, 8))
    monkeypatch.setattr("ansiblectl.domain.context.os.getpid", lambda: next(process_ids))
    monkeypatch.setattr("ansiblectl.domain.context.time.time_ns", lambda: 1_000_000_000)
    monkeypatch.setattr("ansiblectl.domain.context.secrets.randbits", lambda bits: next(randomness))
    generator = _OperationIdGenerator()

    parent_id = generator.new()
    child_id = generator.new()

    assert parent_id != child_id
    assert parent_id < child_id


def test_factory_creates_a_complete_immutable_command_context() -> None:
    context = create_command_context(
        "repository sync",
        debug=True,
        output_format="json",
        interactive=False,
    )

    assert context.command_name == "repository sync"
    assert context.debug is True
    assert context.output_format == "json"
    assert context.interactive is False
    assert len(context.operation_id) == 26
    with pytest.raises(FrozenInstanceError):
        context.command_name = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("operation_id", "command_name", "output_format", "message"),
    [
        ("invalid", "status", "text", "canonical 26-character ULID"),
        (
            "00000000Z80000000000000000",
            " ",
            "text",
            "lowercase command tokens",
        ),
        (
            "00000000Z80000000000000000",
            "repository sync /private/path",
            "text",
            "lowercase command tokens",
        ),
        ("00000000Z80000000000000000", "status", "xml", "text, json, or yaml"),
    ],
)
def test_command_context_rejects_invalid_public_metadata(
    operation_id: str, command_name: str, output_format: str, message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        CommandContext(operation_id, command_name, False, output_format, True)


@pytest.mark.parametrize(
    ("debug", "interactive"),
    [(1, True), (False, "yes")],
)
def test_command_context_requires_runtime_boolean_flags(debug: object, interactive: object) -> None:
    with pytest.raises(ValidationError, match="must be boolean values"):
        CommandContext(
            "00000000Z80000000000000000",
            "status",
            debug,  # type: ignore[arg-type]
            "text",
            interactive,  # type: ignore[arg-type]
        )


def test_invalid_output_format_is_not_retained_in_error_context() -> None:
    with pytest.raises(ValidationError) as raised:
        CommandContext(
            "00000000Z80000000000000000",
            "status",
            False,
            "token-do-not-expose",
            True,
        )

    assert raised.value.context == {}
    assert "do-not-expose" not in str(raised.value)
