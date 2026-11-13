import ipaddress
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.auth import CurrentUser, Identity, current_identity, current_profile, current_user
from app.deps import DbSession
from app.errors import AppError
from app.models import LegalKind, Profile, ProfileStatus, Role
from app.services import accounts, geocoding, legal, service_area

router = APIRouter(tags=["auth"])


class MeProfile(BaseModel):
    role: Role
    status: ProfileStatus
    # Asked for in the person's area after sign-up (CLAUDE.md 6.13), so each may still be empty.
    full_name: str | None
    phone: str | None
    pin_code: str | None
    address: str | None
    relationship_to_child: str | None  # parents only
    details_complete: bool

    @classmethod
    def of(cls, profile: Profile) -> MeProfile:
        return cls(
            role=profile.role,
            status=profile.status,
            full_name=profile.full_name,
            phone=profile.phone,
            pin_code=profile.pin_code,
            address=profile.address,
            relationship_to_child=profile.relationship_to_child,
            details_complete=accounts.details_complete(profile),
        )


class TermsVersion(BaseModel):
    kind: LegalKind
    version: str


class Me(BaseModel):
    email: str | None
    # None until the person finishes sign-up (chooses a role).
    profile: MeProfile | None
    # Current documents this person still has to accept (on their consent page).
    terms_to_accept: list[TermsVersion] = []


def me_for(db: Session, email: str | None, profile: Profile | None) -> Me:
    if profile is None:
        return Me(email=email, profile=None)
    todo = [TermsVersion(kind=doc.kind, version=doc.version) for doc in legal.outstanding(db, profile.id, profile.role)]
    return Me(email=email, profile=MeProfile.of(profile), terms_to_accept=todo)


def request_info(request: Request) -> legal.RequestInfo:
    """The caller's IP (Render's proxy address is replaced by the real one: uvicorn --proxy-headers) and
    browser, for acceptance records."""
    host = request.client.host if request.client else None
    try:
        ip = str(ipaddress.ip_address(host)) if host else None
    except ValueError:
        ip = None
    return legal.RequestInfo(ip_address=ip, user_agent=request.headers.get("user-agent"))


@router.get("/me")
def me(user: Annotated[CurrentUser, Depends(current_user)], db: DbSession) -> Me:
    """Who's signed in, so the web app knows where to send them."""
    return me_for(db, user.identity.email, user.profile)


class AcceptTerms(BaseModel):
    # The kinds and versions the person was shown and ticked to agree to.
    accepted: list[TermsVersion] = Field(max_length=5)

    def items(self) -> list[legal.Accepted]:
        return [legal.Accepted(kind=item.kind, version=item.version) for item in self.accepted]


@router.post("/me/terms")
def accept_terms(
    body: AcceptTerms,
    request: Request,
    profile: Annotated[Profile, Depends(current_profile)],
    user: Annotated[CurrentUser, Depends(current_user)],
    db: DbSession,
) -> Me:
    """Accept the current versions: the sitter consent page, and the parental consent page after a
    new version (first acceptance there goes with the consents, POST /parent/consent)."""
    legal.accept_outstanding(db, profile, body.items(), request_info(request))
    return me_for(db, user.identity.email, profile)


class ServiceArea(BaseModel):
    pin_codes: list[str]


@router.get("/service-area")
def get_service_area(db: DbSession) -> ServiceArea:
    """The pin codes Pacifyco works in, so the sign-up form can check before sending. Public."""
    return ServiceArea(pin_codes=service_area.active_pin_codes(db))


class SignUp(BaseModel):
    """First sign-in: only the role (CLAUDE.md 6.13). The terms are ticked on the consent page and
    everything else comes later too (decided 2026-11-12)."""

    # Admins are never chosen at sign-up (CLAUDE.md 6.13).
    role: Literal["parent", "sitter"]


class Details(BaseModel):
    full_name: str = Field(min_length=1, max_length=100)
    phone: str = Field(max_length=20)
    # Home pin code; must be one of the service-area pin codes (CLAUDE.md 1).
    pin_code: str = Field(pattern=r"^[0-9]{6}$")
    address: str = Field(min_length=1, max_length=300)
    # Parents must give it; sitters leave it out (Reuben, 2026-11-13).
    relationship_to_child: Literal["Mother", "Father", "Legal guardian"] | None = None

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

    @field_validator("address")
    @classmethod
    def _clean_address(cls, value: str) -> str:
        lines = [" ".join(line.split()) for line in value.splitlines()]
        address = "\n".join(line for line in lines if line)
        if not address or any(not ch.isprintable() for ch in address.replace("\n", "")):
            raise ValueError("Please enter your home address")
        return address


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
    )
    return me_for(db, identity.email, profile)


@router.put("/me/details")
def put_details(
    body: Details,
    profile: Annotated[Profile, Depends(current_profile)],
    user: Annotated[CurrentUser, Depends(current_user)],
    geocoder: Annotated[geocoding.Geocoder, Depends(geocoding.get_geocoder)],
    db: DbSession,
) -> Me:
    """Name, mobile, home pin code and address, filled in from the person's area (CLAUDE.md 6.13)."""
    accounts.update_details(
        db,
        profile,
        geocoder,
        full_name=body.full_name,
        phone=body.phone,
        pin_code=body.pin_code,
        address=body.address,
        relationship_to_child=body.relationship_to_child,
    )
    return me_for(db, user.identity.email, profile)
