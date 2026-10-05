"""A small client for the parts of the CookPal API an api key may use."""

from __future__ import annotations

from typing import Any

import aiohttp

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)


class CookpalError(Exception):
    """Anything that went wrong talking to CookPal."""


class CookpalConnectionError(CookpalError):
    """The server could not be reached or answered nonsense."""


class CookpalAuthError(CookpalError):
    """The key is unknown, revoked, or its account can no longer sign in."""


class CookpalForbiddenError(CookpalError):
    """The key lacks the scope this call needs."""


class CookpalNotFoundError(CookpalError):
    """The list is gone, or no longer ours."""


def normalize_url(url: str) -> str:
    """The server's address without trailing slashes, which is how it is stored."""
    return url.strip().rstrip("/")


class CookpalClient:
    """Calls one CookPal server with one api key."""

    def __init__(self, session: aiohttp.ClientSession, url: str, api_key: str) -> None:
        self._session = session
        self._base = f"{normalize_url(url)}/api/v1"
        self._api_key = api_key

    async def get_instance(self) -> dict[str, Any]:
        """What the server offers; needs no key."""
        return await self._request("GET", "/instance", authenticated=False)

    async def get_current_key(self) -> dict[str, Any]:
        """The key itself: its scopes, account id and owner's display name."""
        return await self._request("GET", "/api-keys/current")

    async def get_lists(self) -> list[dict[str, Any]]:
        """Every shopping list the key's account can use."""
        return await self._request("GET", "/shopping/lists")

    async def get_changes(self, list_id: int, household: str | None, since: int) -> dict[str, Any]:
        """What changed on a list since a version, or the whole list when marked full."""
        return await self._request("GET", f"/shopping/lists/{list_id}/changes", params=_list_params(household, since))

    async def apply_ops(
        self, list_id: int, household: str | None, since: int, ops: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Applies ops in order; answers what changed since the version, ours included."""
        return await self._request(
            "POST",
            f"/shopping/lists/{list_id}/ops",
            params=_list_params(household, since),
            json={"ops": ops},
        )

    async def get_unit_words(self) -> list[str]:
        """The catalogue's unit words, which tell "2 kg Mehl" apart from "2 Pizzateige"."""
        vocabulary = await self._request("GET", "/shopping/vocabulary")
        return vocabulary.get("unitWords", [])

    async def _request(
        self,
        method: str,
        path: str,
        *,
        authenticated: bool = True,
        params: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        headers = {"Authorization": f"Bearer {self._api_key}"} if authenticated else {}
        try:
            async with self._session.request(
                method,
                f"{self._base}{path}",
                headers=headers,
                params=params,
                json=json,
                timeout=REQUEST_TIMEOUT,
            ) as response:
                if response.status == 401:
                    raise CookpalAuthError
                if response.status == 403:
                    raise CookpalForbiddenError
                if response.status == 404:
                    raise CookpalNotFoundError
                if response.status >= 400:
                    raise CookpalConnectionError(f"{method} {path} answered {response.status}")
                return await response.json()
        except (aiohttp.ClientError, TimeoutError, ValueError) as error:
            raise CookpalConnectionError(str(error)) from error


def _list_params(household: str | None, since: int) -> dict[str, str]:
    params = {"since": str(since)}
    if household:
        params["household"] = household
    return params
