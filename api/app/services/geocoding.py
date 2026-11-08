"""Turning a home address into a map position, and distances between people (CLAUDE.md 3).

OpenStreetMap's Nominatim: at most one request a second, a User-Agent that names us, and every result
cached (`geocode_cache`) so an address is only looked up once. A failed lookup never blocks saving a
profile: the position stays empty and distance just isn't shown.
"""

import math
import re
import threading
import time
from decimal import Decimal
from typing import Annotated, Protocol

import httpx2 as httpx
from fastapi import Depends
from sqlalchemy.orm import Session

from app.models import GeocodeCache
from app.settings import Settings, get_settings

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "Pacifyco/1.0 (query.pacifyco@gmail.com)"
MIN_SECONDS_BETWEEN_REQUESTS = 1.0
REQUEST_TIMEOUT = 5.0
EARTH_RADIUS_KM = 6371.0

Position = tuple[Decimal, Decimal]


class Geocoder(Protocol):
    def lookup(self, query: str) -> Position | None: ...


class NominatimGeocoder:
    _lock = threading.Lock()  # shared by every instance: the limit is per server, not per request
    _last_request = 0.0

    def lookup(self, query: str) -> Position | None:
        with NominatimGeocoder._lock:
            wait = NominatimGeocoder._last_request + MIN_SECONDS_BETWEEN_REQUESTS - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            try:
                response = httpx.get(
                    NOMINATIM_URL,
                    params={"q": query, "format": "jsonv2", "limit": 1, "countrycodes": "in"},
                    headers={"User-Agent": USER_AGENT},
                    timeout=REQUEST_TIMEOUT,
                )
                response.raise_for_status()
                results = response.json()
            except httpx.HTTPError, ValueError:
                return None
            finally:
                NominatimGeocoder._last_request = time.monotonic()
        if not results:
            return None
        return _round(results[0]["lat"]), _round(results[0]["lon"])


def get_geocoder(settings: Annotated[Settings, Depends(get_settings)]) -> Geocoder:
    return NominatimGeocoder()


def _round(value: str | float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.000001"))


def _normalise(query: str) -> str:
    return re.sub(r"\s+", " ", query.replace("\n", ", ")).strip().lower()


def cached_lookup(db: Session, geocoder: Geocoder, query: str) -> Position | None:
    key = _normalise(query)
    hit = db.get(GeocodeCache, key)
    if hit is not None:
        return hit.lat, hit.lng
    found = geocoder.lookup(key)
    if found is not None:
        db.add(GeocodeCache(query=key, lat=found[0], lng=found[1]))
        db.flush()
    return found


def locate_home(db: Session, geocoder: Geocoder, address: str, pin_code: str) -> Position | None:
    """The full address first; if Nominatim doesn't know it, the pin code's area."""
    return cached_lookup(db, geocoder, f"{address}, {pin_code}, Bengaluru, India") or cached_lookup(
        db, geocoder, f"{pin_code}, Bengaluru, India"
    )


def distance_km(a: tuple[Decimal | None, Decimal | None], b: tuple[Decimal | None, Decimal | None]) -> float | None:
    """Straight-line (haversine) distance, or None if either position is unknown."""
    if None in a or None in b:
        return None
    lat1, lng1, lat2, lng2 = (math.radians(float(v)) for v in (*a, *b))  # type: ignore[arg-type]
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))
