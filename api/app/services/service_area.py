"""Where Pacify works: sign-up (and later booking) only for active launch pin codes (CLAUDE.md 1)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import ServiceAreaPincode


def active_pin_codes(db: Session) -> list[str]:
    return list(
        db.scalars(
            select(ServiceAreaPincode.pin_code)
            .where(ServiceAreaPincode.active.is_(True))
            .order_by(ServiceAreaPincode.pin_code)
        )
    )


def require_in_service_area(db: Session, pin_code: str) -> None:
    area = db.get(ServiceAreaPincode, pin_code)
    if area is None or not area.active:
        raise AppError(422, "outside_service_area", "Pacify isn't available in this pin code yet")
