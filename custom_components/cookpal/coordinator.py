"""Keeps one shopping list in sync, the way the app does: by version, asking only for what changed."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
import uuid

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    CookpalAuthError,
    CookpalClient,
    CookpalError,
    CookpalForbiddenError,
    CookpalNotFoundError,
)
from .const import DOMAIN, LIST_SCAN_INTERVAL, LOGGER

type Item = dict[str, Any]


@dataclass
class CookpalData:
    """What one config entry holds while it is loaded."""

    client: CookpalClient
    scopes: set[str]
    unit_words: set[str] = field(default_factory=set)
    coordinators: dict[int, CookpalListCoordinator] = field(default_factory=dict)


type CookpalConfigEntry = ConfigEntry[CookpalData]


class CookpalListCoordinator(DataUpdateCoordinator[dict[str, Item]]):
    """The items of one list, by id, without deleted ones."""

    config_entry: CookpalConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: CookpalConfigEntry,
        client: CookpalClient,
        shopping_list: dict[str, Any],
    ) -> None:
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} list {shopping_list['id']}",
            update_interval=LIST_SCAN_INTERVAL,
        )
        self.client = client
        self.shopping_list = shopping_list
        self.list_id: int = shopping_list["id"]
        self.household: str | None = shopping_list.get("householdId")
        self._items: dict[str, Item] = {}
        self._version = 0
        # Polls and writes both move the version; one at a time keeps it from going backwards.
        self._lock = asyncio.Lock()

    async def _async_update_data(self) -> dict[str, Item]:
        async with self._lock:
            try:
                changes = await self.client.get_changes(self.list_id, self.household, self._version)
            except CookpalAuthError as error:
                raise ConfigEntryAuthFailed from error
            except CookpalNotFoundError as error:
                self._report_gone()
                raise UpdateFailed(f"Shopping list {self.list_id} is gone") from error
            except CookpalError as error:
                raise UpdateFailed(str(error)) from error
            ir.async_delete_issue(self.hass, DOMAIN, self._gone_issue_id)
            return self._take(changes)

    async def async_apply(self, ops: list[Item]) -> None:
        """Sends what HA changed and takes in the answer, which also carries other devices' changes."""
        for op in ops:
            op.setdefault("opId", str(uuid.uuid4()))
        async with self._lock:
            try:
                changes = await self.client.apply_ops(self.list_id, self.household, self._version, ops)
            except CookpalAuthError as error:
                self.config_entry.async_start_reauth(self.hass)
                raise HomeAssistantError(translation_domain=DOMAIN, translation_key="auth_failed") from error
            except CookpalForbiddenError as error:
                raise HomeAssistantError(translation_domain=DOMAIN, translation_key="read_only") from error
            except CookpalError as error:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="update_failed",
                    translation_placeholders={"error": str(error)},
                ) from error
            self.async_set_updated_data(self._take(changes))

    def _take(self, changes: dict[str, Any]) -> dict[str, Item]:
        if changes.get("full"):
            self._items = {}
        for item in changes.get("items", []):
            if item.get("deleted"):
                self._items.pop(item["id"], None)
            else:
                self._items[item["id"]] = item
        self._version = changes.get("version", self._version)
        return dict(self._items)

    @property
    def _gone_issue_id(self) -> str:
        return list_gone_issue_id(self.config_entry, self.list_id)

    def _report_gone(self) -> None:
        report_list_gone(self.hass, self.config_entry, self.list_id)


def list_gone_issue_id(entry: ConfigEntry, list_id: int) -> str:
    """One repair issue per picked list that no longer exists."""
    return f"list_gone_{entry.entry_id}_{list_id}"


def report_list_gone(hass: HomeAssistant, entry: ConfigEntry, list_id: int) -> None:
    """Points to the options, where the list can be unpicked."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        list_gone_issue_id(entry, list_id),
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="list_gone",
        translation_placeholders={"entry": entry.title},
    )
