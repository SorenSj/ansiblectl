"""Public SDK test utilities for plugin authors."""

from ansiblectl.sdk.context import SDKContext


def mock_context(*capabilities: str) -> SDKContext:
    """Build a capability-scoped test context without core startup."""

    return SDKContext(frozenset(capabilities))
