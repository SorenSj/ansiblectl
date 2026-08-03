"""Per-invocation command context and operation identifier generation."""

from __future__ import annotations

import os
import re
import secrets
import threading
import time
from dataclasses import dataclass

from ansiblectl.domain.errors import ValidationError

_ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ULID_PATTERN = re.compile(r"^[0-7][0-9A-HJKMNP-TV-Z]{25}$")
_COMMAND_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]*(?: [a-z][a-z0-9-]*)*$")
_MAX_TIMESTAMP = (1 << 48) - 1
_MAX_RANDOMNESS = (1 << 80) - 1
_OUTPUT_FORMATS = frozenset({"text", "json", "yaml"})


class _OperationIdGenerator:
    """Generate monotonic ULIDs safely across concurrent callers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._process_id = os.getpid()
        self._last_timestamp = -1
        self._last_randomness = -1

    def new(self) -> str:
        with self._lock:
            process_id = os.getpid()
            if process_id != self._process_id:
                self._process_id = process_id
                self._last_timestamp = -1
                self._last_randomness = -1
            timestamp = time.time_ns() // 1_000_000
            if timestamp > self._last_timestamp:
                randomness = secrets.randbits(80)
            else:
                timestamp = self._last_timestamp
                randomness = self._last_randomness + 1
                if randomness > _MAX_RANDOMNESS:
                    timestamp += 1
                    randomness = secrets.randbits(80)
            operation_id = _encode_ulid(timestamp, randomness)
            self._last_timestamp = timestamp
            self._last_randomness = randomness
            return operation_id


_OPERATION_ID_GENERATOR = _OperationIdGenerator()


@dataclass(frozen=True)
class CommandContext:
    """Stable operational metadata for one command invocation."""

    operation_id: str
    command_name: str
    debug: bool
    output_format: str
    interactive: bool

    def __post_init__(self) -> None:
        if not isinstance(self.operation_id, str) or not _ULID_PATTERN.fullmatch(self.operation_id):
            raise ValidationError("Operation ID must be a canonical 26-character ULID.")
        if not isinstance(self.command_name, str) or not _COMMAND_NAME_PATTERN.fullmatch(
            self.command_name
        ):
            raise ValidationError(
                "Command name must contain only lowercase command tokens.",
                hint="Use command and subcommand names without argument values.",
            )
        if not isinstance(self.debug, bool) or not isinstance(self.interactive, bool):
            raise ValidationError("Command debug and interactive flags must be boolean values.")
        if not isinstance(self.output_format, str) or self.output_format not in _OUTPUT_FORMATS:
            raise ValidationError(
                "Command output format must be one of: text, json, or yaml.",
            )


def create_command_context(
    command_name: str,
    *,
    debug: bool = False,
    output_format: str = "text",
    interactive: bool = True,
) -> CommandContext:
    """Create a context with one fresh operation ID for a CLI invocation."""

    return CommandContext(
        operation_id=new_operation_id(),
        command_name=command_name,
        debug=debug,
        output_format=output_format,
        interactive=interactive,
    )


def new_operation_id() -> str:
    """Return a process-monotonic ULID using millisecond time and secure randomness."""

    return _OPERATION_ID_GENERATOR.new()


def _encode_ulid(timestamp: int, randomness: int) -> str:
    if not 0 <= timestamp <= _MAX_TIMESTAMP:
        raise ValueError("ULID timestamp must fit in 48 bits.")
    if not 0 <= randomness <= _MAX_RANDOMNESS:
        raise ValueError("ULID randomness must fit in 80 bits.")

    value = (timestamp << 80) | randomness
    encoded = ["0"] * 26
    for index in range(25, -1, -1):
        encoded[index] = _ULID_ALPHABET[value & 0b11111]
        value >>= 5
    return "".join(encoded)


__all__ = ["CommandContext", "create_command_context", "new_operation_id"]
