"""Plans and pricing (CLAUDE.md 6.1 and 9 "Plans and pricing"): price per plan and children, Pause one
child only, Unwind +₹150 per extra child, Recharge flat, whole hours only."""

import pytest

from app.errors import AppError
from app.models import SitterLevel as Plan
from app.services import pricing


@pytest.mark.parametrize(
    ("plan", "children", "paise"),
    [
        (Plan.pause, 1, 49_900),
        (Plan.unwind, 1, 69_900),
        (Plan.unwind, 2, 84_900),  # ₹849, the example in CLAUDE.md
        (Plan.unwind, 4, 114_900),
        (Plan.recharge, 1, 89_900),
        (Plan.recharge, 5, 89_900),  # the same for any number
    ],
)
def test_hourly_price(plan, children, paise):
    assert pricing.hourly_price_paise(plan, children) == paise


def test_booking_price_is_hourly_price_times_hours():
    assert pricing.booking_price_paise(Plan.recharge, 2, 3) == 269_700  # ₹2,697, the example in CLAUDE.md
    assert pricing.booking_price_paise(Plan.unwind, 2, 2) == 169_800


def test_pause_takes_one_child_only():
    with pytest.raises(AppError) as error:
        pricing.hourly_price_paise(Plan.pause, 2)
    assert error.value.code == "one_child_only"


@pytest.mark.parametrize("children", [0, -1])
def test_a_booking_needs_a_child(children):
    with pytest.raises(AppError) as error:
        pricing.hourly_price_paise(Plan.unwind, children)
    assert error.value.code == "no_children"


@pytest.mark.parametrize("hours", [0, -2, 1.5, 2.0, True])
def test_whole_hours_only(hours):
    with pytest.raises(AppError) as error:
        pricing.booking_price_paise(Plan.unwind, 1, hours)
    assert error.value.code == "whole_hours_only"
