"""Tests for the FireBrick config flow."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import patch

import aiohttp
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.firebrick.const import CONF_SCAN_INTERVAL, DOMAIN

from .conftest import SERIAL, URL, USER_INPUT


async def test_user_flow(
    hass: HomeAssistant, mock_firebrick: Callable[..., None]
) -> None:
    """A valid router creates an entry keyed by serial number."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    with patch("custom_components.firebrick.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**USER_INPUT, CONF_URL: "firebrick.test/"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"FireBrick {SERIAL}"
    assert result["result"].unique_id == SERIAL
    assert result["data"][CONF_URL] == URL


async def test_user_flow_invalid_auth(
    hass: HomeAssistant, mock_firebrick: Callable[..., None]
) -> None:
    """The router's redirect to /login/ is reported as invalid auth."""
    mock_firebrick(status=303)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_cannot_connect(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Network errors are reported as cannot_connect."""
    aioclient_mock.get(f"{URL}/system/info", exc=aiohttp.ClientError())
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_already_configured(
    hass: HomeAssistant,
    mock_firebrick: Callable[..., None],
    mock_config_entry: MockConfigEntry,
) -> None:
    """The same router can't be added twice."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth(
    hass: HomeAssistant,
    mock_firebrick: Callable[..., None],
    mock_config_entry: MockConfigEntry,
) -> None:
    """Reauth stores the new credentials."""
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    with patch("custom_components.firebrick.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: "homeassistant", CONF_PASSWORD: "new"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_PASSWORD] == "new"


async def test_options_flow(
    hass: HomeAssistant,
    mock_firebrick: Callable[..., None],
    mock_config_entry: MockConfigEntry,
) -> None:
    """The polling interval can be changed."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 60}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options == {CONF_SCAN_INTERVAL: 60}
    assert mock_config_entry.runtime_data.update_interval.total_seconds() == 60
