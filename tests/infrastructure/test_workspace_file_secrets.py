"""Private workspace file secret provider contract tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ansiblectl.domain.secrets import SecretNotFoundError, SecretReference
from ansiblectl.infrastructure import workspace_file_secrets
from ansiblectl.infrastructure.workspace_file_secrets import WorkspaceFileSecretProvider

_MESSAGE = "Secret material is unavailable from the selected provider."


def private_secret(tmp_path: Path, content: bytes = b"sentinel-secret-value") -> Path:
    private = tmp_path / ".ansiblectl"
    private.mkdir(mode=0o700)
    private.chmod(0o700)
    secrets = private / "secrets"
    secrets.mkdir(mode=0o700)
    secrets.chmod(0o700)
    secret = secrets / "WEBHOOK_KEY"
    secret.write_bytes(content)
    secret.chmod(0o600)
    return secret


def resolve(tmp_path: Path, key: str = "WEBHOOK_KEY") -> str:
    material = WorkspaceFileSecretProvider(tmp_path).resolve(SecretReference("file", key))
    return material.reveal_for_operation()


@pytest.mark.parametrize("key", ["A", "WEBHOOK_KEY", "A" + "1_" * 31 + "X"])
def test_provider_resolves_exact_canonical_private_file(tmp_path: Path, key: str) -> None:
    secret = private_secret(tmp_path)
    secret.rename(secret.with_name(key))

    material = WorkspaceFileSecretProvider(tmp_path).resolve(SecretReference("file", key))

    assert material.reveal_for_operation() == "sentinel-secret-value"
    assert "sentinel-secret-value" not in repr(material)
    assert "sentinel-secret-value" not in repr(WorkspaceFileSecretProvider(tmp_path))


@pytest.mark.parametrize(
    "provider,key",
    [
        ("env", "WEBHOOK_KEY"),
        ("file", "lowercase"),
        ("file", "1KEY"),
        ("file", "KEY-NAME"),
        ("file", "KEY.NAME"),
        ("file", "../KEY"),
        ("file", "Æ_KEY"),
        ("file", "A" * 65),
    ],
)
def test_invalid_reference_fails_without_exposing_identity(
    tmp_path: Path, provider: str, key: str
) -> None:
    with pytest.raises(SecretNotFoundError) as caught:
        WorkspaceFileSecretProvider(tmp_path).resolve(SecretReference(provider, key))

    assert str(caught.value) == _MESSAGE
    assert key not in str(caught.value)


@pytest.mark.parametrize(
    "content",
    [b"", b"line\nfeed", b"terminal\n", b"nul\x00", b"del\x7f", b"c1\xc2\x85", b"\xff"],
)
def test_invalid_material_has_one_redacted_failure(tmp_path: Path, content: bytes) -> None:
    private_secret(tmp_path, content)

    with pytest.raises(SecretNotFoundError) as caught:
        resolve(tmp_path)

    assert str(caught.value) == _MESSAGE
    assert "WEBHOOK_KEY" not in str(caught.value)


def test_exact_material_size_boundary(tmp_path: Path) -> None:
    private_secret(tmp_path, b"X" * 8192)
    assert resolve(tmp_path) == "X" * 8192

    (tmp_path / ".ansiblectl/secrets/WEBHOOK_KEY").write_bytes(b"X" * 8193)
    with pytest.raises(SecretNotFoundError, match=_MESSAGE):
        resolve(tmp_path)


@pytest.mark.parametrize("component", ["private", "secrets", "material"])
def test_symlink_at_every_controlled_component_is_rejected(tmp_path: Path, component: str) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    if component == "private":
        (tmp_path / ".ansiblectl").symlink_to(outside, target_is_directory=True)
    else:
        private = tmp_path / ".ansiblectl"
        private.mkdir(mode=0o700)
        private.chmod(0o700)
        if component == "secrets":
            (private / "secrets").symlink_to(outside, target_is_directory=True)
        else:
            secrets = private / "secrets"
            secrets.mkdir(mode=0o700)
            secrets.chmod(0o700)
            target = outside / "material"
            target.write_text("sentinel-secret-value", encoding="utf-8")
            (secrets / "WEBHOOK_KEY").symlink_to(target)

    with pytest.raises(SecretNotFoundError, match=_MESSAGE):
        resolve(tmp_path)


@pytest.mark.parametrize("component", ["private", "secrets", "material"])
def test_group_or_other_permissions_are_rejected(tmp_path: Path, component: str) -> None:
    secret = private_secret(tmp_path)
    selected = {
        "private": tmp_path / ".ansiblectl",
        "secrets": tmp_path / ".ansiblectl/secrets",
        "material": secret,
    }[component]
    selected.chmod(0o640 if component == "material" else 0o750)

    with pytest.raises(SecretNotFoundError, match=_MESSAGE):
        resolve(tmp_path)


def test_hard_linked_material_is_rejected(tmp_path: Path) -> None:
    secret = private_secret(tmp_path)
    os.link(secret, secret.with_name("SECOND_LINK"))

    with pytest.raises(SecretNotFoundError, match=_MESSAGE):
        resolve(tmp_path)


def test_non_regular_material_is_rejected_without_blocking(tmp_path: Path) -> None:
    secret = private_secret(tmp_path)
    secret.unlink()
    os.mkfifo(secret, mode=0o600)

    with pytest.raises(SecretNotFoundError, match=_MESSAGE):
        resolve(tmp_path)


def test_missing_objects_and_underlying_details_are_redacted(tmp_path: Path) -> None:
    provider = WorkspaceFileSecretProvider(tmp_path / "sentinel-private-root")

    with pytest.raises(SecretNotFoundError) as caught:
        provider.resolve(SecretReference("file", "SENTINEL_SECRET_KEY"))

    assert str(caught.value) == _MESSAGE
    assert caught.value.__cause__ is None
    assert "sentinel" not in str(caught.value).lower()


def test_unsupported_open_capabilities_fail_before_filesystem_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "ansiblectl.infrastructure.workspace_file_secrets._has_required_open_capabilities",
        lambda: False,
    )

    with pytest.raises(SecretNotFoundError, match=_MESSAGE):
        resolve(tmp_path)


def test_owner_mismatch_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    private_secret(tmp_path)
    monkeypatch.setattr(os, "geteuid", lambda: os.stat(tmp_path).st_uid + 1)

    with pytest.raises(SecretNotFoundError, match=_MESSAGE):
        resolve(tmp_path)


def test_atomic_rotation_is_observed_only_by_the_next_resolution(tmp_path: Path) -> None:
    secret = private_secret(tmp_path, b"first-private-value")
    provider = WorkspaceFileSecretProvider(tmp_path)

    first = provider.resolve(SecretReference("file", "WEBHOOK_KEY"))
    replacement = secret.with_name("REPLACEMENT")
    replacement.write_bytes(b"second-private-value")
    replacement.chmod(0o600)
    replacement.replace(secret)
    second = provider.resolve(SecretReference("file", "WEBHOOK_KEY"))

    assert first.reveal_for_operation() == "first-private-value"
    assert second.reveal_for_operation() == "second-private-value"


def test_replacement_after_validation_reads_the_validated_descriptor_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = private_secret(tmp_path, b"validated-private-value")
    original_read = os.read
    replaced = False

    def replacing_read(descriptor: int, size: int) -> bytes:
        nonlocal replaced
        if not replaced:
            replacement = secret.with_name("REPLACEMENT")
            replacement.write_bytes(b"attacker-controlled-value")
            replacement.chmod(0o600)
            replacement.replace(secret)
            replaced = True
        return original_read(descriptor, size)

    monkeypatch.setattr(os, "read", replacing_read)

    assert resolve(tmp_path) == "validated-private-value"
    assert replaced is True


def test_directory_replacement_cannot_redirect_descriptor_relative_material_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = private_secret(tmp_path, b"validated-directory-value")
    secrets = secret.parent
    moved = secrets.with_name("validated-secrets")
    original_open_material = workspace_file_secrets._open_material

    def replacing_open(name: str, *, directory_fd: int) -> int:
        secrets.rename(moved)
        secrets.mkdir(mode=0o700)
        secrets.chmod(0o700)
        attacker = secrets / name
        attacker.write_bytes(b"attacker-controlled-value")
        attacker.chmod(0o600)
        return original_open_material(name, directory_fd=directory_fd)

    monkeypatch.setattr(
        "ansiblectl.infrastructure.workspace_file_secrets._open_material", replacing_open
    )

    assert resolve(tmp_path) == "validated-directory-value"
