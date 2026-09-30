"""Constants for the Cookpal integration."""

from datetime import timedelta
import logging

DOMAIN = "cookpal"
LOGGER = logging.getLogger(__package__)

DEFAULT_URL = "https://beta.cookpal.io"

CONF_LISTS = "lists"

SCOPE_SHOPPING_READ = "shopping:read"
SCOPE_SHOPPING_WRITE = "shopping:write"

LIST_SCAN_INTERVAL = timedelta(seconds=30)
VOCABULARY_REFRESH_INTERVAL = timedelta(hours=24)
