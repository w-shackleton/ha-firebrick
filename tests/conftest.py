"""Shared fixtures for FireBrick tests."""

from __future__ import annotations

from collections.abc import Callable, Generator
from pathlib import Path
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, CONF_VERIFY_SSL

from custom_components.firebrick.const import DOMAIN

FIXTURES = Path(__file__).parent / "fixtures"
URL = "https://firebrick.test"
SERIAL = "2900-0815-0234"
USER_INPUT = {
    CONF_URL: URL,
    CONF_USERNAME: "homeassistant",
    CONF_PASSWORD: "secret",
    CONF_VERIFY_SSL: True,
}


def load_fixture(name: str) -> str:
    """Return the contents of a fixture file."""
    return (FIXTURES / name).read_text()


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom_components/ in every test."""


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """A configured FireBrick entry."""
    return MockConfigEntry(
        domain=DOMAIN, unique_id=SERIAL, title=f"FireBrick {SERIAL}", data=USER_INPUT
    )


@pytest.fixture
def mock_firebrick(
    aioclient_mock: AiohttpClientMocker,
) -> Callable[..., None]:
    """Serve captured router responses. Call again to swap the ports sample."""

    def _register(ports: str = "ports_1.xml", status: int = 200) -> None:
        aioclient_mock.clear_requests()
        responses = {
            "/system/info": load_fixture("system_info.html"),
            "/status/ports/.xml": load_fixture(ports),
            "/status/pppoe/xml": load_fixture("pppoe.xml"),
            "/cqm/json/": load_fixture("cqm_index.html"),
            "/cqm/pppoe.json": load_fixture("cqm_pppoe.json"),
            "/cqm/home.json": load_fixture("cqm_home.json"),
        }
        for path, text in responses.items():
            aioclient_mock.get(f"{URL}{path}", text=text, status=status)

    _register()
    return _register


@pytest.fixture
def mock_monotonic() -> Generator[list[float]]:
    """Control the coordinator's clock: append/replace values to advance it."""
    clock = [1000.0]
    with patch(
        "custom_components.firebrick.coordinator.monotonic",
        side_effect=lambda: clock[0],
    ):
        yield clock
