"""Checks against a real Supabase project that tests can't make (CLAUDE.md 9 "Security testing"; phase 12):
the browser's public key can't read the tables, the documents bucket is private, nothing in it can be read
without a signed URL, and a signed URL stops working once it expires. (An empty table also reads as
"refused", so run it on staging, which has seed data.)

Run by Reuben against staging, with the keys typed into his own terminal (never into code or chat):

    SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... SUPABASE_ANON_KEY=... python -m app.cli check-supabase

It uploads one tiny test file under `security-check/`, then deletes it. Nothing else is touched. With the
public (anon, or publishable) key it also checks that the browser can't read the tables (RLS).
"""

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

import httpx2 as httpx

from app.services.storage import BUCKET

# A 1x1 PNG, so a bucket that only takes images and PDFs still accepts the test file.
PROBE = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)
EXPIRES_IN = 2  # seconds: long enough to read it once, short enough to wait out


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


def check_storage(url: str, key: str, sleep: Callable[[float], None] = time.sleep) -> list[Check]:
    base = f"{url.rstrip('/')}/storage/v1"
    service = {"apikey": key, "Authorization": f"Bearer {key}"}
    path = f"security-check/{uuid.uuid4()}.png"
    found: list[Check] = []

    bucket = httpx.get(f"{base}/bucket/{BUCKET}", headers=service, timeout=10)
    public = bucket.json().get("public") if bucket.status_code == 200 else None
    found.append(Check("The documents bucket is private", public is False, f"public={public}"))

    signed = httpx.post(f"{base}/object/upload/sign/{BUCKET}/{path}", headers=service, json={}, timeout=10)
    signed.raise_for_status()
    upload = httpx.put(
        f"{base}/object/upload/sign/{BUCKET}/{path}?token={signed.json()['token']}",
        content=PROBE,
        headers={"Content-Type": "image/png"},
        timeout=10,
    )
    upload.raise_for_status()
    try:
        anonymous = httpx.get(f"{base}/object/public/{BUCKET}/{path}", timeout=10)
        found.append(
            Check("A file can't be read without a signed URL", anonymous.status_code != 200, str(anonymous.status_code))
        )
        bare = httpx.get(f"{base}/object/{BUCKET}/{path}", timeout=10)
        found.append(Check("A file can't be read without a key", bare.status_code != 200, str(bare.status_code)))

        view = httpx.post(
            f"{base}/object/sign/{BUCKET}/{path}", headers=service, json={"expiresIn": EXPIRES_IN}, timeout=10
        )
        view.raise_for_status()
        link = f"{base}{view.json()['signedURL']}"
        fresh = httpx.get(link, timeout=10)
        found.append(Check("A signed URL works while it's valid", fresh.status_code == 200, str(fresh.status_code)))
        sleep(EXPIRES_IN + 3)
        stale = httpx.get(link, timeout=10)
        found.append(Check("A signed URL stops working once expired", stale.status_code != 200, str(stale.status_code)))
    finally:
        httpx.request("DELETE", f"{base}/object/{BUCKET}", headers=service, json={"prefixes": [path]}, timeout=10)
    return found


# Tables the browser's public (anon) key must not read through Supabase's REST API (CLAUDE.md 5: RLS on
# every table, no policies for the browser roles). A sample of the most personal ones.
PRIVATE_TABLES = ("profiles", "children", "documents", "payments", "bookings", "sitters", "messages", "audit_log")


def _error_code(response) -> str:
    """Supabase's REST error code (such as 42501 or PGRST002), never any data."""
    try:
        body = response.json()
    except ValueError:
        return ""
    return str(body.get("code", "")) if isinstance(body, dict) else ""


def check_tables(url: str, anon_key: str) -> list[Check]:
    """Asks Supabase's REST API for rows with the public key, as a browser could. Passes only on a real
    answer: refused (401/403, or permission denied), not exposed at all (404), or allowed but no rows (RLS
    with no policies). Anything else, a 5xx above all, means the table wasn't actually tested, so it fails."""
    found = []
    headers = {"apikey": anon_key, "Authorization": f"Bearer {anon_key}"}
    for table in PRIVATE_TABLES:
        response = httpx.get(f"{url.rstrip('/')}/rest/v1/{table}?select=*&limit=1", headers=headers, timeout=10)
        code = _error_code(response)
        if response.status_code == 200:
            rows = response.json()
            passed, detail = rows == [], "200, no rows" if rows == [] else "200, rows came back"
        elif response.status_code in (401, 403, 404):
            passed, detail = True, f"{response.status_code} {code}".strip()
        else:
            passed = False
            detail = f"{response.status_code} {code}: not tested, the REST API didn't answer properly".replace(
                " :", ":"
            )
        found.append(Check(f"The public key can't read {table}", passed, detail))
    return found
