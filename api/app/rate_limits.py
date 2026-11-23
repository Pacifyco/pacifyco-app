"""Rate limits on sign-up, booking, paying, complaints and uploads (CLAUDE.md 9 "Security testing"; slowapi
approved by Reuben, 2026-11-23).

Counted per signed-in user (the verified token's user id, which a caller can't change the way they could an
IP header), in a moving window, in memory on the API instance (one Render service, so one count). Sign-in
itself (the email code and Google) is Supabase Auth's, which has its own rate limits.

The limits are generous for a real person and stop a script hammering an endpoint:
"""

from typing import Annotated

from fastapi import Depends
from limits import parse
from slowapi import Limiter

from app.auth import Identity, current_identity
from app.errors import AppError

SIGN_UP = "5/minute"
BOOKING = "20/hour"
PAYMENT = "10/hour"  # sending a UPI reference, for a booking or a charge
COMPLAINT = "10/hour"
MESSAGE = "30/hour"  # writing on a complaint
UPLOAD = "30/hour"

# slowapi's limiter holds the counts; it's used through a dependency (below) rather than its decorator, so
# limits apply after the token is verified and are keyed by who's signed in.
limiter = Limiter(key_func=lambda _request: "", strategy="moving-window", storage_uri="memory://")


def rate_limited(limit: str, scope: str):
    """A dependency: 429 `rate_limited` once this user has used `limit` for `scope`."""
    item = parse(limit)

    def check(identity: Annotated[Identity, Depends(current_identity)]) -> None:
        if not limiter.limiter.hit(item, scope, str(identity.user_id)):
            raise AppError(429, "rate_limited", "You're doing that a lot. Please wait a little and try again.")

    return Depends(check)
