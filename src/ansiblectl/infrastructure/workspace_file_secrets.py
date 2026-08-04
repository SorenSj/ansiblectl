"""Descriptor-relative resolution of private workspace secret files."""

from __future__ import annotations

import os
import re
import stat
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

from ansiblectl.domain.secrets import SecretMaterial, SecretNotFoundError, SecretReference

_FILE_SECRET_KEY = re.compile(r"[A-Z][A-Z0-9_]{0,63}", re.ASCII)
_MAX_MATERIAL_BYTES = 8192
_UNAVAILABLE_MESSAGE = "Secret material is unavailable from the selected provider."


@dataclass(frozen=True)
class WorkspaceFileSecretProvider:
    """Resolve one canonical ``file`` reference beneath a fixed private directory."""

    workspace_root: Path = field(repr=False)

    def resolve(self, reference: SecretReference) -> SecretMaterial:
        if reference.provider != "file" or _FILE_SECRET_KEY.fullmatch(reference.key) is None:
            raise SecretNotFoundError(_UNAVAILABLE_MESSAGE)
        if not _has_required_open_capabilities():
            raise SecretNotFoundError(_UNAVAILABLE_MESSAGE)

        descriptors: list[int] = []
        try:
            root_fd = _open_directory(self.workspace_root)
            descriptors.append(root_fd)
            private_fd = _open_directory(".ansiblectl", directory_fd=root_fd)
            descriptors.append(private_fd)
            _validate_private_directory(private_fd)
            secrets_fd = _open_directory("secrets", directory_fd=private_fd)
            descriptors.append(secrets_fd)
            directory = _validate_private_directory(secrets_fd)

            material_fd = _open_material(reference.key, directory_fd=secrets_fd)
            descriptors.append(material_fd)
            _validate_material_file(material_fd, directory.st_dev)
            value = _read_material(material_fd)
        except Exception:
            raise SecretNotFoundError(_UNAVAILABLE_MESSAGE) from None
        finally:
            for descriptor in reversed(descriptors):
                with suppress(OSError):
                    os.close(descriptor)

        return SecretMaterial(value)


def _has_required_open_capabilities() -> bool:
    return (
        hasattr(os, "O_CLOEXEC")
        and hasattr(os, "O_DIRECTORY")
        and hasattr(os, "O_NOFOLLOW")
        and os.open in os.supports_dir_fd
    )


def _open_directory(path: str | Path, *, directory_fd: int | None = None) -> int:
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    if directory_fd is None:
        return os.open(path, flags)
    return os.open(path, flags, dir_fd=directory_fd)


def _open_material(name: str, *, directory_fd: int) -> int:
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    return os.open(name, flags, dir_fd=directory_fd)


def _validate_private_directory(descriptor: int) -> os.stat_result:
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise OSError
    return metadata


def _validate_material_file(descriptor: int, directory_device: int) -> None:
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
        or metadata.st_dev != directory_device
        or stat.S_IMODE(metadata.st_mode) & 0o077
        or metadata.st_size > _MAX_MATERIAL_BYTES
    ):
        raise OSError


def _read_material(descriptor: int) -> str:
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = os.read(descriptor, _MAX_MATERIAL_BYTES + 1 - size)
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
        if size > _MAX_MATERIAL_BYTES:
            raise OSError
    content = b"".join(chunks)
    if not content or len(content) > _MAX_MATERIAL_BYTES:
        raise OSError
    value = content.decode("utf-8", errors="strict")
    if any(_is_control(character) for character in value):
        raise OSError
    return value


def _is_control(character: str) -> bool:
    codepoint = ord(character)
    return codepoint <= 31 or 127 <= codepoint <= 159


__all__ = ["WorkspaceFileSecretProvider"]
