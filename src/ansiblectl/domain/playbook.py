"""Safe playbook selection within a declared content root."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from ansiblectl.domain.errors import DomainError


class PlaybookError(DomainError):
    """Raised when a requested playbook cannot be safely selected."""


@dataclass(frozen=True)
class PlaybookReference:
    path: Path
    revision: str
    findings: tuple[str, ...] = ()


def select_playbook(content_root: Path, identifier: Path, revision: str) -> PlaybookReference:
    """Resolve a supported existing YAML playbook without allowing root escape."""

    root = content_root.resolve()
    candidate = (
        (root / identifier).resolve() if not identifier.is_absolute() else identifier.resolve()
    )
    if not candidate.is_relative_to(root):
        raise PlaybookError("Playbook path escapes the declared content root.")
    if not candidate.is_file():
        raise PlaybookError(
            "Playbook does not exist. Select an existing file within the content root."
        )
    if candidate.suffix not in {".yml", ".yaml"}:
        raise PlaybookError("Playbook must use a supported .yml or .yaml file extension.")
    return PlaybookReference(candidate, revision)


def playbook_digest(reference: PlaybookReference) -> str:
    """Hash the exact validated playbook bytes selected for execution."""

    try:
        content = reference.path.read_bytes()
    except OSError as error:
        raise PlaybookError("Selected playbook became unreadable before execution.") from error
    return f"sha256:{hashlib.sha256(content).hexdigest()}"
