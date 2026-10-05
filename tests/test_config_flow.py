"""Connecting an account, picking lists, and swapping in a new key."""

from __future__ import annotations

import aiohttp
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.cookpal.const import CONF_LISTS, DOMAIN

from .conftest import ACCOUNT_ID, API, HOUSEHOLD_LIST, KEY, OWN_LIST, URL, mock_server


async def test_connects_and_suggests_the_own_list(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    mock_server(aioclient_mock)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": f"{URL}/", "api_key": KEY})
    assert result["step_id"] == "lists"
    schema = result["data_schema"].schema
    assert next(iter(schema)).default() == [str(OWN_LIST)]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LISTS: [str(OWN_LIST), str(HOUSEHOLD_LIST)]}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "CookPal (Anna)"
    assert result["data"] == {"url": URL, "api_key": KEY}
    assert result["options"] == {CONF_LISTS: [str(OWN_LIST), str(HOUSEHOLD_LIST)]}
    assert result["result"].unique_id == f"{URL}#{ACCOUNT_ID}"


@pytest.mark.parametrize(
    ("mock", "error"),
    [
        (lambda m: m.get(f"{API}/instance", exc=aiohttp.ClientError()), "cannot_connect"),
        (lambda m: mock_server(m, api_keys_enabled=False), "api_keys_disabled"),
        (lambda m: mock_server(m, scopes=()), "missing_scope"),
    ],
)
async def test_explains_why_it_cannot_connect(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock, error: str
) -> None:
    mock(aioclient_mock)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": URL, "api_key": KEY})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_a_revoked_key_is_invalid(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"{API}/instance", json={"apiKeysEnabled": True})
    aioclient_mock.get(f"{API}/api-keys/current", status=401)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": URL, "api_key": KEY})

    assert result["errors"] == {"base": "invalid_auth"}


async def test_an_account_is_connected_once(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    mock_server(aioclient_mock)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": URL, "api_key": "cpk_other"})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_takes_a_new_key_of_the_same_account(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    mock_server(aioclient_mock)

    result = await config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": "cpk_new"})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data["api_key"] == "cpk_new"


async def test_reauth_refuses_another_accounts_key(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    aioclient_mock.get(f"{API}/instance", json={"apiKeysEnabled": True})
    aioclient_mock.get(
        f"{API}/api-keys/current",
        json={"id": 2, "name": "x", "scopes": ["shopping:read"], "accountId": ACCOUNT_ID + 1, "owner": "Bert"},
    )

    result = await config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": "cpk_bert"})

    assert result["reason"] == "wrong_account"
    assert config_entry.data["api_key"] == KEY


async def test_options_pick_the_lists_again(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    mock_server(aioclient_mock)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_LISTS: [str(HOUSEHOLD_LIST)]})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options == {CONF_LISTS: [str(HOUSEHOLD_LIST)]}
    assert hass.states.get("todo.cookpal_familie_shopping_list") is not None
    assert hass.states.get("todo.cookpal_shopping_list") is None
