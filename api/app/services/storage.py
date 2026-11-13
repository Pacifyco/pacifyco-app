"""Talks to Supabase Storage's REST API using the service-role key (CLAUDE.md section 5): uploads go
through signed upload URLs issued by the API, and files are viewed only through short-lived signed
URLs. The service-role key bypasses Storage's own access rules and never reaches the browser.

Swappable in tests via the `get_storage` dependency, the same way app.auth swaps in a fake KeySource."""

from typing import Annotated, Protocol

import httpx2 as httpx
from fastapi import Depends

from app.errors import AppError
from app.settings import Settings, get_settings

BUCKET = "documents"
VIEW_URL_EXPIRY_SECONDS = 120
REQUEST_TIMEOUT = 10


class StorageClient(Protocol):
    def create_signed_upload_url(self, path: str) -> str: ...

    def create_signed_view_url(self, path: str) -> str: ...

    def download(self, path: str) -> bytes: ...

    def delete(self, path: str) -> None: ...


UNAVAILABLE_MESSAGE = "Pacifyco's file storage isn't available right now. Please try again."


class SupabaseStorage:
    """The real client, talking to `{SUPABASE_URL}/storage/v1`."""

    def __init__(self, settings: Settings) -> None:
        self._base = f"{settings.supabase_url.rstrip('/')}/storage/v1"
        self._headers = {
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
        }

    def create_signed_upload_url(self, path: str) -> str:
        url = f"{self._base}/object/upload/sign/{BUCKET}/{path}"
        try:
            response = httpx.post(url, headers=self._headers, json={}, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AppError(503, "storage_unavailable", UNAVAILABLE_MESSAGE) from exc
        # The client PUTs the file straight to this URL; the token is what authorises it, not a key.
        return f"{url}?token={response.json()['token']}"

    def create_signed_view_url(self, path: str) -> str:
        url = f"{self._base}/object/sign/{BUCKET}/{path}"
        try:
            response = httpx.post(
                url, headers=self._headers, json={"expiresIn": VIEW_URL_EXPIRY_SECONDS}, timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AppError(503, "storage_unavailable", UNAVAILABLE_MESSAGE) from exc
        return f"{self._base}{response.json()['signedURL']}"

    def download(self, path: str) -> bytes:
        url = f"{self._base}/object/{BUCKET}/{path}"
        try:
            response = httpx.get(url, headers=self._headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise AppError(404, "storage_object_not_found", "That file doesn't exist in storage") from exc
            raise AppError(503, "storage_unavailable", UNAVAILABLE_MESSAGE) from exc
        except httpx.HTTPError as exc:
            raise AppError(503, "storage_unavailable", UNAVAILABLE_MESSAGE) from exc
        return response.content

    def delete(self, path: str) -> None:
        url = f"{self._base}/object/{BUCKET}"
        try:
            response = httpx.request(
                "DELETE", url, headers=self._headers, json={"prefixes": [path]}, timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AppError(503, "storage_unavailable", UNAVAILABLE_MESSAGE) from exc


def get_storage(settings: Annotated[Settings, Depends(get_settings)]) -> StorageClient:
    return SupabaseStorage(settings)
