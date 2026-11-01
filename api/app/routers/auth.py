from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from app.auth import CurrentUser, Identity, current_identity, current_user
from app.deps import DbSession
from app.errors import AppError
from app.models import Profile, ProfileStatus, Role
from app.services import accounts, service_area

router = APIRouter(tags=["auth"])


class MeProfile(BaseModel):
    role: Role
    status: ProfileStatus
    full_name: str

    @classmethod
    def of(cls, profile: Profile) -> MeProfile:
        return cls(role=profile.role, status=profile.status, full_name=profile.full_name)


class Me(BaseModel):
    email: str | None
    # None until the person finishes sign-up (chooses a role).
    profile: MeProfile | None


@router.get("/me")
def me(user: Annotated[CurrentUser, Depends(current_user)]) -> Me:
    """Who's signed in, so the web app knows where to send them."""
    return Me(email=user.identity.email, profile=MeProfile.of(user.profile) if user.profile else None)


class ServiceArea(BaseModel):
    pin_codes: list[str]


@router.get("/service-area")
def get_service_area(db: DbSession) -> ServiceArea:
    """The pin codes Pacify works in, so the sign-up form can check before sending. Public."""
    return ServiceArea(pin_codes=service_area.active_pin_codes(db))


class SignUp(BaseModel):
    # Admins are never chosen at sign-up (CLAUDE.md 6.13).
    role: Literal["parent", "sitter"]
    full_name: str = Field(min_length=1, max_length=100)
    phone: str = Field(max_length=20)
    # Home pin code; must be one of the launch pin codes (CLAUDE.md 1).
    pin_code: str = Field(pattern=r"^[0-9]{6}$")

    @field_validator("full_name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        name = " ".join(value.split())
        if not name or any(not ch.isprintable() for ch in name):
            raise ValueError("Please enter your full name")
        return name

    @field_validator("phone")
    @classmethod
    def _indian_mobile(cls, value: str) -> str:
        phone = accounts.normalise_mobile(value)
        if phone is None:
            raise ValueError("Please enter a 10-digit Indian mobile number")
        return phone


@router.post("/me/profile", status_code=201)
def sign_up(body: SignUp, identity: Annotated[Identity, Depends(current_identity)], db: DbSession) -> Me:
    """Finish sign-up: choose parent or sitter. Once only; the role can't be changed by the user."""
    if not identity.email:
        raise AppError(422, "email_required", "Please sign in with an email address")
    profile = accounts.sign_up(
        db,
        user_id=identity.user_id,
        email=identity.email,
        role=Role(body.role),
        full_name=body.full_name,
        phone=body.phone,
        pin_code=body.pin_code,
    )
    return Me(email=identity.email, profile=MeProfile.of(profile))
