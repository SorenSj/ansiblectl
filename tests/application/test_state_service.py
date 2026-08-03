"""Workspace-state inspection tests."""

from ansiblectl.application.state import CacheEntrySummary, StateService
from ansiblectl.domain.state import CacheEntry, StateInvalidationResult


class FakeStatePort:
    def read(self) -> dict[str, CacheEntry]:
        return {"inventory": CacheEntry("git:main", "revision changes", {"secret": "hidden"})}

    def write(self, entries: dict[str, CacheEntry]) -> None:
        raise AssertionError("Inspection must not write state.")

    def invalidate(self, name: str, *, apply: bool) -> StateInvalidationResult:
        return StateInvalidationResult(name, True, apply, 0)


def test_state_inspection_returns_metadata_without_cached_value() -> None:
    assert StateService(FakeStatePort()).inspect() == (
        CacheEntrySummary("inventory", "git:main", "revision changes"),
    )


def test_state_invalidation_delegates_explicit_apply_choice() -> None:
    assert StateService(FakeStatePort()).invalidate("inventory", apply=True) == (
        StateInvalidationResult("inventory", True, True, 0)
    )
