"""Each picked CookPal shopping list as a to-do list."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
import uuid

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SCOPE_SHOPPING_WRITE
from .coordinator import CookpalConfigEntry, CookpalListCoordinator, Item
from .quick_add import parse_quick_add, tidy_name

PARALLEL_UPDATES = 0

WRITE_FEATURES = (
    TodoListEntityFeature.CREATE_TODO_ITEM
    | TodoListEntityFeature.UPDATE_TODO_ITEM
    | TodoListEntityFeature.DELETE_TODO_ITEM
    | TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CookpalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """One entity per picked list."""
    async_add_entities(CookpalTodoList(coordinator) for coordinator in entry.runtime_data.coordinators.values())


class CookpalTodoList(CoordinatorEntity[CookpalListCoordinator], TodoListEntity):
    """A shopping list. Bought items show as completed, as long as the app keeps them as recently bought."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: CookpalListCoordinator) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        shopping_list = coordinator.shopping_list
        self._attr_unique_id = f"{entry.unique_id}_{coordinator.list_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(entry.unique_id))},
            name="CookPal",
            manufacturer="CookPal",
            entry_type=DeviceEntryType.SERVICE,
        )
        if shopping_list.get("name"):
            self._attr_name = shopping_list["name"]
        elif shopping_list.get("householdName"):
            self._attr_translation_key = "household_default_list"
            self._attr_translation_placeholders = {"household": shopping_list["householdName"]}
        else:
            self._attr_translation_key = "default_list"
        if SCOPE_SHOPPING_WRITE in entry.runtime_data.scopes:
            self._attr_supported_features = WRITE_FEATURES

    @property
    def todo_items(self) -> list[TodoItem]:
        """Open items oldest first, as they were put on the list; bought ones newest first."""
        items = self.coordinator.data.values()
        active = sorted(
            (item for item in items if item["status"] == "ACTIVE"), key=lambda item: _instant(item.get("addedAt"))
        )
        bought = sorted(
            (item for item in items if item["status"] != "ACTIVE"),
            key=lambda item: _instant(item.get("boughtAt")),
            reverse=True,
        )
        return [_to_todo_item(item) for item in [*active, *bought]]

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Splits "2 Liter Milch" like the app does; a description given in HA wins over the parsed amount."""
        name, spec = parse_quick_add(item.summary or "", self.coordinator.config_entry.runtime_data.unit_words)
        if item.description:
            spec = item.description
        await self.coordinator.async_apply([{"type": "ADD", "itemId": str(uuid.uuid4()), "name": name, "spec": spec}])

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Renames, changes the amount, and ticks or unticks, as one batch."""
        current = self.coordinator.data.get(item.uid or "")
        if current is None:
            return
        ops: list[dict[str, Any]] = []
        update: dict[str, Any] = {}
        if item.summary is not None and tidy_name(item.summary) and tidy_name(item.summary) != current["name"]:
            update["name"] = tidy_name(item.summary)
        if (item.description or "") != (current.get("spec") or ""):
            # Blank clears the amount on the server.
            update["spec"] = item.description or ""
        if update:
            ops.append({"type": "UPDATE", "itemId": current["id"], **update})
        is_active = current["status"] == "ACTIVE"
        if item.status == TodoItemStatus.COMPLETED and is_active:
            ops.append({"type": "BUY", "itemId": current["id"]})
        elif item.status == TodoItemStatus.NEEDS_ACTION and not is_active:
            # Unticking keeps what was asked for, like undoing a tick in the app.
            ops.append({"type": "RESTORE", "itemId": current["id"], "spec": update.get("spec", current.get("spec"))})
        if ops:
            await self.coordinator.async_apply(ops)

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Also what "Remove completed" calls, with the bought items."""
        await self.coordinator.async_apply([{"type": "DELETE", "itemId": uid} for uid in uids])


def _to_todo_item(item: Item) -> TodoItem:
    bought = item["status"] != "ACTIVE"
    return TodoItem(
        uid=item["id"],
        summary=item["name"],
        description=item.get("spec"),
        status=TodoItemStatus.COMPLETED if bought else TodoItemStatus.NEEDS_ACTION,
        completed=_instant(item.get("boughtAt")) if bought and item.get("boughtAt") else None,
    )


def _instant(value: str | None) -> datetime:
    # Parsed rather than compared as text: the server leaves out trailing zeros of the fraction.
    return datetime.fromisoformat(value) if value else datetime.min.replace(tzinfo=UTC)
