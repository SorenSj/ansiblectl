"""Central recursive redaction for values crossing public boundaries."""

from __future__ import annotations

import re
from collections.abc import Mapping

REDACTED_VALUE = "<redacted>"
_CIRCULAR_REFERENCE = "<circular-reference>"
_MAXIMUM_DEPTH = "<maximum-depth>"
_MAX_DEPTH = 64
_SENSITIVE_PARTS = frozenset({"credential", "key", "password", "secret", "token"})


def redact(value: object) -> object:
    """Return a recursively copied value with sensitive named fields replaced."""

    return _redact(value, set(), 0)


def _redact(value: object, active: set[int], depth: int) -> object:
    """Redact one value while bounding recursive public-data traversal."""

    if isinstance(value, Mapping):
        if depth >= _MAX_DEPTH:
            return _MAXIMUM_DEPTH
        identity = id(value)
        if identity in active:
            return _CIRCULAR_REFERENCE
        active.add(identity)
        try:
            return {
                name: REDACTED_VALUE if _is_sensitive(name) else _redact(item, active, depth + 1)
                for name, item in value.items()
            }
        finally:
            active.remove(identity)
    if isinstance(value, (list, tuple)):
        if depth >= _MAX_DEPTH:
            return _MAXIMUM_DEPTH
        identity = id(value)
        if identity in active:
            return _CIRCULAR_REFERENCE
        active.add(identity)
        try:
            return [_redact(item, active, depth + 1) for item in value]
        finally:
            active.remove(identity)
    return value


def _is_sensitive(name: object) -> bool:
    if not isinstance(name, str):
        return False
    parts = re.split(r"[^a-z0-9]+", name.lower())
    return any(
        part in _SENSITIVE_PARTS or part.removesuffix("s") in _SENSITIVE_PARTS for part in parts
    )


__all__ = ["REDACTED_VALUE", "redact"]
