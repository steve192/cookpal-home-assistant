"""A shopping list as a to-do list: what it shows and the ops HA's changes turn into."""

from __future__ import annotations

from typing import Any

from homeassistant.components.todo import DOMAIN as TODO_DOMAIN, TodoServices
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceNotSupported
from homeassistant.helpers import issue_registry as ir
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.cookpal.const import CONF_LISTS, DOMAIN

from .conftest import API, OWN_LIST, item, mock_server

ENTITY = "todo.cookpal_shopping_list"


async def setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def sent_ops(aioclient_mock: AiohttpClientMocker) -> list[dict[str, Any]]:
    return [op for method, url, body, _ in aioclient_mock.mock_calls if method == "POST" for op in body["ops"]]


async def test_shows_open_items_and_recently_bought_ones(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    mock_server(
        aioclient_mock,
        items=[
            item("a", "Milch", spec="2 l"),
            item("b", "Brot", status="BOUGHT", boughtAt="2026-09-29T11:00:00.5Z"),
        ],
    )
    await setup(hass, config_entry)

    assert hass.states.get(ENTITY).state == "1"
    result = await hass.services.async_call(
        TODO_DOMAIN, TodoServices.GET_ITEMS, {ATTR_ENTITY_ID: ENTITY}, blocking=True, return_response=True
    )
    items = result[ENTITY]["items"]
    assert [(entry["summary"], entry["status"]) for entry in items] == [
        ("Milch", "needs_action"),
        ("Brot", "completed"),
    ]
    assert items[0]["description"] == "2 l"


async def test_adding_splits_the_amount_off_like_the_app(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    mock_server(aioclient_mock)
    await setup(hass, config_entry)

    await hass.services.async_call(
        TODO_DOMAIN, TodoServices.ADD_ITEM, {ATTR_ENTITY_ID: ENTITY, "item": "2 kg Kartoffeln"}, blocking=True
    )

    [op] = sent_ops(aioclient_mock)
    assert (op["type"], op["name"], op["spec"]) == ("ADD", "Kartoffeln", "2 kg")
    assert op["opId"] and op["itemId"]


async def test_ticking_buys_and_unticking_restores(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    mock_server(aioclient_mock, items=[item("a", "Milch", spec="2 l"), item("b", "Brot", status="BOUGHT")])
    await setup(hass, config_entry)

    await hass.services.async_call(
        TODO_DOMAIN,
        TodoServices.UPDATE_ITEM,
        {ATTR_ENTITY_ID: ENTITY, "item": "a", "status": "completed"},
        blocking=True,
    )
    await hass.services.async_call(
        TODO_DOMAIN,
        TodoServices.UPDATE_ITEM,
        {ATTR_ENTITY_ID: ENTITY, "item": "b", "status": "needs_action"},
        blocking=True,
    )

    assert [(op["type"], op["itemId"]) for op in sent_ops(aioclient_mock)] == [("BUY", "a"), ("RESTORE", "b")]


async def test_renaming_and_clearing_the_amount_is_one_update(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    mock_server(aioclient_mock, items=[item("a", "Milch", spec="2 l")])
    await setup(hass, config_entry)

    await hass.services.async_call(
        TODO_DOMAIN,
        TodoServices.UPDATE_ITEM,
        {ATTR_ENTITY_ID: ENTITY, "item": "a", "rename": "Hafermilch", "description": ""},
        blocking=True,
    )

    [op] = sent_ops(aioclient_mock)
    assert (op["type"], op["name"], op["spec"]) == ("UPDATE", "Hafermilch", "")


async def test_removing_completed_deletes_the_bought_items(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    mock_server(aioclient_mock, items=[item("a", "Milch"), item("b", "Brot", status="BOUGHT")])
    await setup(hass, config_entry)

    await hass.services.async_call(
        TODO_DOMAIN, TodoServices.REMOVE_COMPLETED_ITEMS, {ATTR_ENTITY_ID: ENTITY}, blocking=True
    )

    assert [(op["type"], op["itemId"]) for op in sent_ops(aioclient_mock)] == [("DELETE", "b")]


async def test_a_read_only_key_cannot_change_the_list(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    mock_server(aioclient_mock, scopes=("shopping:read",))
    await setup(hass, config_entry)

    with pytest.raises(ServiceNotSupported):
        await hass.services.async_call(
            TODO_DOMAIN, TodoServices.ADD_ITEM, {ATTR_ENTITY_ID: ENTITY, "item": "Milch"}, blocking=True
        )


async def test_a_revoked_key_asks_for_a_new_one(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    aioclient_mock.get(f"{API}/api-keys/current", status=401)
    await setup(hass, config_entry)

    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]


async def test_a_picked_list_that_is_gone_is_reported(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, issue_registry: ir.IssueRegistry
) -> None:
    mock_server(aioclient_mock)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="gone",
        data={"url": "https://cookpal.test", "api_key": "cpk_secret"},
        options={CONF_LISTS: [str(OWN_LIST), "99"]},
    )
    await setup(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert issue_registry.async_get_issue(DOMAIN, f"list_gone_{entry.entry_id}_99") is not None
