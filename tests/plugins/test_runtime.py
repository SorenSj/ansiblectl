"""Plugin lifecycle tests."""

from dataclasses import dataclass, field

from ansiblectl.domain.plugins import ProviderDescriptor
from ansiblectl.plugins.runtime import PluginRuntime
from ansiblectl.sdk.context import SDKContext


def _descriptor(identity: str, permissions: tuple[str, ...] = ()) -> ProviderDescriptor:
    return ProviderDescriptor(
        identity, "1.0", "0.1", (), "schema.json", permissions, f"{identity}.yaml"
    )


@dataclass
class FakePlugin:
    fail: bool = False
    contexts: list[SDKContext] = field(default_factory=list)
    shut_down: bool = False

    def initialize(self, context: SDKContext) -> tuple[str, ...]:
        self.contexts.append(context)
        if self.fail:
            raise RuntimeError("boom")
        return ("provider",)

    def shutdown(self) -> None:
        self.shut_down = True


def test_failed_optional_plugin_leaves_no_partial_registration_and_healthy_plugin_continues() -> (
    None
):
    runtime = PluginRuntime()

    assert runtime.load(_descriptor("bad"), FakePlugin(fail=True), frozenset()) is False
    healthy = FakePlugin()
    assert runtime.load(_descriptor("good", ("network",)), healthy, frozenset({"network"})) is True

    assert runtime.registered_capabilities == {"good": ("provider",)}
    assert healthy.contexts == [SDKContext(frozenset({"network"}))]


def test_shutdown_is_called_for_initialised_plugin() -> None:
    runtime, plugin = PluginRuntime(), FakePlugin()
    runtime.load(_descriptor("good"), plugin, frozenset())

    runtime.shutdown()

    assert plugin.shut_down is True


def test_runtime_denies_ungranted_permissions_before_plugin_initialization() -> None:
    runtime, plugin = PluginRuntime(), FakePlugin()

    assert runtime.load(
        _descriptor("limited", ("network", "secrets")), plugin, frozenset({"network"})
    )

    assert plugin.contexts == [SDKContext(frozenset({"network"}))]
    assert runtime.diagnostics == ["Plugin 'limited' denied permission 'secrets' by policy."]


def test_runtime_rejects_unknown_permissions_before_plugin_initialization() -> None:
    runtime, plugin = PluginRuntime(), FakePlugin()

    assert runtime.load(_descriptor("unsafe", ("subprocess",)), plugin, frozenset()) is False

    assert plugin.contexts == []
    assert runtime.diagnostics == ["Optional plugin 'unsafe' failed: PermissionDeniedError."]
