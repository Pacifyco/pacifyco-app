"""What a booking costs the parent (CLAUDE.md 6.1). Money is integer paise; time is whole hours.

The plan comes from the sitter's level (6.2): a sitter works only her own level's plan. Parents see the
rate, never the plan's name (Reuben, 2026-11-17). Sitter pay is not here; it is never shown to parents.
"""

from dataclasses import dataclass

from app.errors import AppError
from app.models import SitterLevel as Plan


@dataclass(frozen=True)
class Rate:
    first_child_paise: int  # the hourly price for one child
    extra_child_paise: int  # added per hour for each child after the first (0: same price for any number)
    max_children: int | None  # None: any number


RATES: dict[Plan, Rate] = {
    Plan.pause: Rate(first_child_paise=49_900, extra_child_paise=0, max_children=1),
    Plan.unwind: Rate(first_child_paise=69_900, extra_child_paise=15_000, max_children=None),
    Plan.recharge: Rate(first_child_paise=89_900, extra_child_paise=0, max_children=None),
}


def hourly_price_paise(plan: Plan, children: int) -> int:
    """The plan's price per hour for this many children (Unwind: +₹150 per extra child)."""
    rate = RATES[plan]
    if children < 1:
        raise AppError(422, "no_children", "Please choose at least one child for this booking.")
    if rate.max_children is not None and children > rate.max_children:
        raise AppError(422, "one_child_only", "This sitter looks after one child at a time.")
    return rate.first_child_paise + rate.extra_child_paise * (children - 1)


def booking_price_paise(plan: Plan, children: int, hours: int) -> int:
    """Hourly price × booked hours. Bookings are whole hours only (decided 2026-11-03); no GST for now."""
    if isinstance(hours, bool) or not isinstance(hours, int) or hours < 1:
        raise AppError(422, "whole_hours_only", "Bookings are made in whole hours.")
    return hourly_price_paise(plan, children) * hours
