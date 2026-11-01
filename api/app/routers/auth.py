from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import CurrentUser, current_user
from app.models import ProfileStatus, Role

router = APIRouter(tags=["auth"])


class MeProfile(BaseModel):
    role: Role
    status: ProfileStatus
    full_name: str


class Me(BaseModel):
    email: str | None
    # None until the person finishes sign-up (chooses a role and accepts the terms).
    profile: MeProfile | None


@router.get("/me")
def me(user: Annotated[CurrentUser, Depends(current_user)]) -> Me:
    """Who's signed in, so the web app knows where to send them."""
    profile = user.profile
    return Me(
        email=user.identity.email,
        profile=MeProfile(role=profile.role, status=profile.status, full_name=profile.full_name) if profile else None,
    )
