"""Connecting Home Assistant to a Cookpal account with an api key."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.const import CONF_API_KEY, CONF_URL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import voluptuous as vol

from .api import CookpalAuthError, CookpalClient, CookpalError, normalize_url
from .const import CONF_LISTS, DEFAULT_URL, DOMAIN, LOGGER, SCOPE_SHOPPING_READ
from .coordinator import CookpalConfigEntry, list_gone_issue_id

KEY_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


class CannotConnect(Exception):
    """Carries the form error to show."""

    def __init__(self, error: str) -> None:
        super().__init__(error)
        self.error = error


async def _check_key(hass: HomeAssistant, url: str, api_key: str) -> tuple[CookpalClient, dict[str, Any]]:
    """The client and the key's own description, or the reason the form shows."""
    client = CookpalClient(async_get_clientsession(hass), url, api_key)
    try:
        instance = await client.get_instance()
        if not instance.get("apiKeysEnabled"):
            raise CannotConnect("api_keys_disabled")
        key = await client.get_current_key()
    except CookpalAuthError as error:
        raise CannotConnect("invalid_auth") from error
    except CookpalError as error:
        LOGGER.debug("Cannot reach Cookpal at %s: %s", url, error)
        raise CannotConnect("cannot_connect") from error
    if SCOPE_SHOPPING_READ not in key.get("scopes", []):
        raise CannotConnect("missing_scope")
    return client, key


def _list_options(lists: list[dict[str, Any]]) -> list[SelectOptionDict]:
    def label(shopping_list: dict[str, Any]) -> str:
        household = shopping_list.get("householdName")
        name = shopping_list.get("name") or ("Shopping list" if household is None else household)
        return f"{name} ({household})" if household and shopping_list.get("name") else name

    return [SelectOptionDict(value=str(shopping_list["id"]), label=label(shopping_list)) for shopping_list in lists]


def _lists_schema(lists: list[dict[str, Any]], picked: list[str]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_LISTS, default=picked): SelectSelector(
                SelectSelectorConfig(options=_list_options(lists), multiple=True)
            )
        }
    )


class CookpalConfigFlow(ConfigFlow, domain=DOMAIN):
    """Server and key first, then which lists to show."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._owner = ""
        self._lists: list[dict[str, Any]] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Where the server is and which key to use."""
        errors: dict[str, str] = {}
        if user_input is not None:
            url = normalize_url(user_input[CONF_URL])
            try:
                client, key = await _check_key(self.hass, url, user_input[CONF_API_KEY])
                self._lists = await client.get_lists()
            except CannotConnect as error:
                errors["base"] = error.error
            except CookpalError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(f"{url}#{key['accountId']}")
                self._abort_if_unique_id_configured()
                self._data = {CONF_URL: url, CONF_API_KEY: user_input[CONF_API_KEY]}
                self._owner = key.get("owner", "")
                return await self.async_step_lists()

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required(CONF_URL): str, vol.Required(CONF_API_KEY): KEY_SELECTOR}),
                user_input or {CONF_URL: DEFAULT_URL},
            ),
            errors=errors,
        )

    async def async_step_lists(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Which lists become to-do lists; the own default list is suggested."""
        if user_input is not None:
            return self.async_create_entry(
                title=f"Cookpal ({self._owner})" if self._owner else "Cookpal",
                data=self._data,
                options={CONF_LISTS: user_input[CONF_LISTS]},
            )
        suggested = [
            str(shopping_list["id"])
            for shopping_list in self._lists
            if shopping_list.get("defaultList") and shopping_list.get("householdId") is None
        ]
        return self.async_show_form(step_id="lists", data_schema=_lists_schema(self._lists, suggested))

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """The key was revoked, or its account can no longer sign in."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """A new key for the same account."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            url = entry.data[CONF_URL]
            try:
                _client, key = await _check_key(self.hass, url, user_input[CONF_API_KEY])
            except CannotConnect as error:
                errors["base"] = error.error
            else:
                await self.async_set_unique_id(f"{url}#{key['accountId']}")
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(entry, data_updates={CONF_API_KEY: user_input[CONF_API_KEY]})

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): KEY_SELECTOR}),
            description_placeholders={"url": entry.data[CONF_URL]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: CookpalConfigEntry) -> CookpalOptionsFlow:
        """Picking lists again."""
        return CookpalOptionsFlow()


class CookpalOptionsFlow(OptionsFlowWithReload):
    """Which lists are shown; reloads so entities follow."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """The same picker as during setup, with what is picked now."""
        if user_input is not None:
            for list_id in self.config_entry.options.get(CONF_LISTS, []):
                if list_id not in user_input[CONF_LISTS]:
                    ir.async_delete_issue(self.hass, DOMAIN, list_gone_issue_id(self.config_entry, int(list_id)))
            return self.async_create_entry(data={CONF_LISTS: user_input[CONF_LISTS]})

        try:
            lists = await self.config_entry.runtime_data.client.get_lists()
        except CookpalError:
            return self.async_abort(reason="cannot_connect")
        known = {str(shopping_list["id"]) for shopping_list in lists}
        picked = [list_id for list_id in self.config_entry.options.get(CONF_LISTS, []) if list_id in known]
        return self.async_show_form(step_id="init", data_schema=_lists_schema(lists, picked))
