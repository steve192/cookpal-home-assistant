"""Splits typed text into a name and an amount, like the Cookpal app's quick add.

A port of parseQuickAdd in the app (src/helper/shopping/quickAdd.ts); change both together.
"""

from __future__ import annotations

from collections.abc import Set
import re

# [0-9] rather than \d: the app's regular expressions only count ASCII digits.
_AMOUNT = r"(?:[0-9]+(?:[.,][0-9]+)?(?:\s*/\s*[0-9]+)?|[½¼¾])"
_LEADING = re.compile(rf"^({_AMOUNT})\s*([^\s0-9]+)?\s+(.+)$")
_TRAILING = re.compile(rf"^(.+?)\s+({_AMOUNT})\s*([^\s0-9]+)?$")


def tidy_name(name: str) -> str:
    """A name as typed, trimmed and single-spaced."""
    return re.sub(r"\s+", " ", name).strip()


def name_key(name: str) -> str:
    """How names are compared: trimmed, single-spaced and lower case."""
    return tidy_name(name).lower()


def parse_quick_add(typed: str, unit_words: Set[str]) -> tuple[str, str | None]:
    """Reads "2 kg Kartoffeln" and "Kartoffeln 2 kg" both as Kartoffeln, 2 kg.

    The unit words make "2 kg" an amount and not the start of a name as in "2 pizza doughs".
    """

    def is_unit(word: str | None) -> bool:
        return word is not None and name_key(word) in unit_words

    text = tidy_name(typed)
    if leading := _LEADING.match(text):
        amount, word, rest = leading.groups()
        if is_unit(word):
            return rest, text[: len(text) - len(rest)].strip()
        return (f"{word} {rest}" if word else rest), amount
    trailing = _TRAILING.match(text)
    if trailing and (trailing.group(3) is None or is_unit(trailing.group(3))):
        name = trailing.group(1)
        return name, text[len(name) :].strip()
    return text, None
