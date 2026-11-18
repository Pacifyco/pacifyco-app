"""What a sitter earns (CLAUDE.md 6.2). Money is integer paise; time is whole hours.

Pay is per hour by her level, the same whatever the number of children. It is never shown to parents,
and sitters never see the plan's name or the price the parent paid.
"""

from app.models import SitterLevel

PAY_PER_HOUR_PAISE: dict[SitterLevel, int] = {
    SitterLevel.pause: 20_000,
    SitterLevel.unwind: 30_000,
    SitterLevel.recharge: 40_000,
}


def booking_pay_paise(level: SitterLevel, hours: int) -> int:
    """Her pay for the booked hours. What she's finally paid is for hours worked, check-in to the booked
    end (6.2), worked out at check-out (phase 8)."""
    return PAY_PER_HOUR_PAISE[level] * hours
