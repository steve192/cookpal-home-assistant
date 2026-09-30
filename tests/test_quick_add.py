"""The same cases as the app's quickAdd.test.ts, so both read typed text alike."""

import pytest

from custom_components.cookpal.quick_add import parse_quick_add

UNITS = {"g", "kg", "l", "netz"}


@pytest.mark.parametrize(
    ("typed", "name", "spec"),
    [
        ("2 kg Kartoffeln", "Kartoffeln", "2 kg"),
        ("Kartoffeln 2 kg", "Kartoffeln", "2 kg"),
        ("500g Mehl", "Mehl", "500g"),
        ("1,5 l Milch", "Milch", "1,5 l"),
        ("3 Äpfel", "Äpfel", "3"),
        ("Eier 10", "Eier", "10"),
        ("1 Netz Zwiebeln", "Zwiebeln", "1 Netz"),
    ],
)
def test_reads_name_and_amount(typed: str, name: str, spec: str) -> None:
    assert parse_quick_add(typed, UNITS) == (name, spec)


def test_keeps_a_word_after_a_number_in_the_name_when_it_is_no_unit() -> None:
    assert parse_quick_add("2 pizza doughs", UNITS) == ("pizza doughs", "2")


def test_leaves_a_name_without_an_amount_alone() -> None:
    assert parse_quick_add("  Klopapier ", UNITS) == ("Klopapier", None)


def test_does_not_take_a_number_inside_a_name_for_an_amount() -> None:
    assert parse_quick_add("Typ 405 Mehl", UNITS) == ("Typ 405 Mehl", None)
