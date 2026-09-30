"""A Cookpal server as far as the integration talks to it."""

from __future__ import annotations

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.cookpal.const import CONF_LISTS, DOMAIN

URL = "https://cookpal.test"
API = f"{URL}/api/v1"
KEY = "cpk_secret"
ACCOUNT_ID = 7
OWN_LIST = 11
HOUSEHOLD_LIST = 12

LISTS = [
    {"id": OWN_LIST, "name": None, "defaultList": True, "householdId": None, "householdName": None, "version": 2},
    {
        "id": HOUSEHOLD_LIST,
        "name": None,
        "defaultList": True,
        "householdId": "h1",
        "householdName": "Familie",
        "version": 0,
    },
]


def item(item_id: str, name: str, **fields: Any) -> dict[str, Any]:
    """An item as the server sends it."""
    return {
        "id": item_id,
        "name": name,
        "spec": None,
        "aisle": "OTHER",
        "status": "ACTIVE",
        "boughtAt": None,
        "addedAt": "2026-09-29T10:00:00Z",
        "deleted": False,
        "version": 1,
        **fields,
    }


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Lets Home Assistant load custom_components/cookpal."""


def mock_server(
    aioclient_mock: AiohttpClientMocker,
    *,
    scopes: tuple[str, ...] = ("shopping:read", "shopping:write"),
    items: list[dict[str, Any]] | None = None,
    api_keys_enabled: bool = True,
) -> None:
    """Answers every call the integration makes, with the own list holding the given items."""
    aioclient_mock.get(f"{API}/instance", json={"apiKeysEnabled": api_keys_enabled})
    aioclient_mock.get(
        f"{API}/api-keys/current",
        json={"id": 1, "name": "Home Assistant", "scopes": list(scopes), "accountId": ACCOUNT_ID, "owner": "Anna"},
    )
    aioclient_mock.get(f"{API}/shopping/lists", json=LISTS)
    aioclient_mock.get(f"{API}/shopping/vocabulary", json={"tiles": [], "unitWords": ["kg", "l", "g"]})
    changes = {"version": 2, "full": True, "items": items or []}
    aioclient_mock.get(f"{API}/shopping/lists/{OWN_LIST}/changes", json=changes)
    aioclient_mock.get(f"{API}/shopping/lists/{HOUSEHOLD_LIST}/changes", json={"version": 0, "full": True, "items": []})
    aioclient_mock.post(f"{API}/shopping/lists/{OWN_LIST}/ops", json={"version": 3, "full": False, "items": []})


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """An entry showing the own list."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Cookpal (Anna)",
        unique_id=f"{URL}#{ACCOUNT_ID}",
        data={"url": URL, "api_key": KEY},
        options={CONF_LISTS: [str(OWN_LIST)]},
    )
