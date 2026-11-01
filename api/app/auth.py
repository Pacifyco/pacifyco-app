"""Who is calling. The web app signs people in with Supabase (email code or Google) and sends the
Supabase access token as `Authorization: Bearer <token>`. We check its signature against the project's
public keys (JWKS), its expiry, audience and issuer, then load the caller's profile and role.

Only asymmetric signing keys (ES256/RS256) are accepted, so the API holds no shared JWT secret."""

import logging
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, Header

from app.deps import DbSession
from app.errors import AppError
from app.models import Profile
from app.settings import Settings, get_settings

logger = logging.getLogger("pacifyco.api")

ALGORITHMS = ["ES256", "RS256"]
AUDIENCE = "authenticated"


@dataclass(frozen=True)
class Identity:
    """A verified Supabase user. They may not have a Pacify profile yet (sign-up comes next)."""

    user_id: uuid.UUID
    email: str | None


@dataclass(frozen=True)
class CurrentUser:
    identity: Identity
    profile: Profile | None


def _unauthorized() -> AppError:
    return AppError(401, "unauthorized", "Please sign in again")


def issuer(settings: Settings) -> str:
    return f"{settings.supabase_url.rstrip('/')}/auth/v1"


def jwks_url(settings: Settings) -> str:
    return settings.supabase_jwks_url or f"{issuer(settings)}/.well-known/jwks.json"


@lru_cache
def _jwks_client_for(url: str) -> jwt.PyJWKClient:
    # Keys are cached for 10 minutes; a token signed by a new key triggers one refetch.
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=600, timeout=5)


class KeySource:
    """Finds the public key a token was signed with. Tests swap in their own keys."""

    def __init__(self, url: str) -> None:
        self.url = url

    def signing_key(self, token: str) -> object:
        return _jwks_client_for(self.url).get_signing_key_from_jwt(token).key


def get_key_source(settings: Annotated[Settings, Depends(get_settings)]) -> KeySource | None:
    if not settings.supabase_url:
        return None
    return KeySource(jwks_url(settings))


def verify_token(token: str, keys: KeySource, settings: Settings) -> Identity:
    try:
        key = keys.signing_key(token)
    except jwt.PyJWKClientConnectionError as exc:
        logger.warning("Couldn't fetch Supabase signing keys")
        raise AppError(503, "auth_unavailable", "Sign-in isn't available right now. Please try again.") from exc
    except jwt.PyJWTError as exc:  # malformed token, or signed by a key that isn't ours
        raise _unauthorized() from exc
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=ALGORITHMS,
            audience=AUDIENCE,
            issuer=issuer(settings),
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
            leeway=30,
        )
        user_id = uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError) as exc:
        raise _unauthorized() from exc
    if claims.get("role") != "authenticated":  # e.g. an anonymous or service token
        raise _unauthorized()
    email = claims.get("email")
    return Identity(user_id=user_id, email=email if isinstance(email, str) and email else None)


def current_identity(
    settings: Annotated[Settings, Depends(get_settings)],
    keys: Annotated[KeySource | None, Depends(get_key_source)],
    authorization: Annotated[str | None, Header()] = None,
) -> Identity:
    """The verified caller. Fails closed: with no SUPABASE_URL configured, nobody is signed in."""
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token or keys is None:
        raise _unauthorized()
    return verify_token(token.strip(), keys, settings)


def current_user(identity: Annotated[Identity, Depends(current_identity)], db: DbSession) -> CurrentUser:
    """The verified caller and their profile (None until they finish signing up)."""
    return CurrentUser(identity=identity, profile=db.get(Profile, identity.user_id))
