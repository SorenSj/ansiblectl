"""SDK public-surface compatibility tests."""

from ansiblectl.sdk import SDK_VERSION, PluginLogger, SDKContext
from ansiblectl.sdk.logging import PluginLogger as PluginLoggerModule
from ansiblectl.sdk.testing import mock_context


def test_sdk_exposes_only_documented_public_symbols() -> None:
    assert SDK_VERSION == "0.1"
    assert set(__import__("ansiblectl.sdk", fromlist=["__all__"]).__all__) == {
        "SDK_VERSION",
        "SDKContext",
        "PluginLogger",
    }


def test_mock_context_supports_plugin_unit_tests_without_core_startup() -> None:
    context = mock_context("network")
    assert isinstance(context, SDKContext)
    assert context.has_capability("network") is True
    assert context.has_capability("secrets") is False


def test_plugin_logger_is_available_from_the_public_sdk_namespace() -> None:
    assert PluginLogger is PluginLoggerModule
