"""The Cookpal integration: Cookpal shopping lists as Home Assistant to-do lists."""

from __future__ import annotations

from datetime import datetime

from homeassistant.const import CONF_API_KEY, CONF_URL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval

from .api import CookpalAuthError, CookpalClient, CookpalError
from .const import CONF_LISTS, LOGGER, VOCABULARY_REFRESH_INTERVAL
from .coordinator import CookpalConfigEntry, CookpalData, CookpalListCoordinator, report_list_gone
from .quick_add import name_key

PLATFORMS: list[Platform] = [Platform.TODO]


async def async_setup_entry(hass: HomeAssistant, entry: CookpalConfigEntry) -> bool:
    """Connects with the entry's key and starts syncing the picked lists."""
    client = CookpalClient(async_get_clientsession(hass), entry.data[CONF_URL], entry.data[CONF_API_KEY])
    try:
        key = await client.get_current_key()
        lists = {shopping_list["id"]: shopping_list for shopping_list in await client.get_lists()}
    except CookpalAuthError as error:
        raise ConfigEntryAuthFailed from error
    except CookpalError as error:
        raise ConfigEntryNotReady(str(error)) from error

    data = CookpalData(client=client, scopes=set(key.get("scopes", [])))
    for list_id in entry.options.get(CONF_LISTS, []):
        shopping_list = lists.get(int(list_id))
        if shopping_list is None:
            report_list_gone(hass, entry, int(list_id))
            continue
        coordinator = CookpalListCoordinator(hass, entry, client, shopping_list)
        await coordinator.async_config_entry_first_refresh()
        data.coordinators[shopping_list["id"]] = coordinator
    entry.runtime_data = data
    _remove_unpicked_lists(hass, entry, data)

    await _refresh_unit_words(data)

    async def refresh_unit_words(_now: datetime) -> None:
        await _refresh_unit_words(data)

    entry.async_on_unload(async_track_time_interval(hass, refresh_unit_words, VOCABULARY_REFRESH_INTERVAL))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CookpalConfigEntry) -> bool:
    """Stops syncing."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


def _remove_unpicked_lists(hass: HomeAssistant, entry: CookpalConfigEntry, data: CookpalData) -> None:
    # Otherwise a list unpicked in the options, or deleted in Cookpal, lingers as unavailable.
    shown = {f"{entry.unique_id}_{list_id}" for list_id in data.coordinators}
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.unique_id not in shown:
            registry.async_remove(entity.entity_id)


async def _refresh_unit_words(data: CookpalData) -> None:
    # Without them items are still added, just with the amount left in the name.
    try:
        data.unit_words = {name_key(word) for word in await data.client.get_unit_words()}
    except CookpalError as error:
        LOGGER.warning("Could not load Cookpal's unit words, adding text unparsed: %s", error)
