import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.errors import CatchUnhandledErrors, register_error_handlers
from app.routers import account, admin, auth, complaints, documents, health, jobs, parents, sitters
from app.settings import Environment, Settings, get_settings

# Collect nothing about parents, children or sitters beyond the error itself: no user details, cookies,
# headers, request bodies, query strings, SQL parameters or local variable values. (The Sentry org also
# refuses to store IP addresses and scrubs passwords and card numbers server-side.)
SENTRY_DATA_COLLECTION = {
    "user_info": False,
    "cookies": False,
    "http_headers": False,
    "http_bodies": [],
    "url_query_params": False,
    "database_query_data": False,
    "queues": False,
    "stack_frame_variables": False,
}


def init_sentry(settings: Settings) -> bool:
    """Turn on Sentry only when SENTRY_DSN is set. Errors only (no tracing). Returns whether it was turned on."""
    if not settings.sentry_dsn:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        send_default_pii=False,
        data_collection=SENTRY_DATA_COLLECTION,
        max_request_body_size="never",
        include_local_variables=False,
        traces_sample_rate=0.0,
    )
    return True


# Every API response (CLAUDE.md 9 "Security testing"). The API only returns JSON, so nothing may run, frame
# or be embedded from it, and nothing personal is cached on the way.
SECURE_HEADERS = {
    b"x-content-type-options": b"nosniff",
    b"x-frame-options": b"DENY",
    b"referrer-policy": b"no-referrer",
    b"content-security-policy": b"default-src 'none'; frame-ancestors 'none'",
    b"cross-origin-resource-policy": b"same-site",
    b"cache-control": b"no-store",
}
HSTS = (b"strict-transport-security", b"max-age=31536000; includeSubDomains")


class SecureHeaders:
    """Adds the security headers to every response, errors included. HSTS outside local (HTTPS only)."""

    def __init__(self, app: ASGIApp, hsts: bool) -> None:
        self.app = app
        self.extra = [*SECURE_HEADERS.items(), *([HSTS] if hsts else [])]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                names = {name.lower() for name, _ in message.get("headers", [])}
                message["headers"] = [
                    *message.get("headers", []),
                    *((name, value) for name, value in self.extra if name not in names),
                ]
            await send(message)

        await self.app(scope, receive, with_headers)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    init_sentry(settings)

    # The interactive docs (and the schema they read) only locally: nobody else needs a map of the API.
    local = settings.environment == Environment.local
    app = FastAPI(
        title="Pacifyco API",
        docs_url="/docs" if local else None,
        redoc_url="/redoc" if local else None,
        openapi_url="/openapi.json" if local else None,
    )
    app.dependency_overrides[get_settings] = lambda: settings

    app.add_middleware(SecureHeaders, hsts=not local)
    # Added first so it sits inside CORS: even crashes get CORS headers (app/errors.py).
    app.add_middleware(CatchUnhandledErrors)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    register_error_handlers(app)
    app.include_router(auth.router)
    app.include_router(health.router)
    app.include_router(jobs.router)
    app.include_router(documents.router)
    app.include_router(complaints.router)
    app.include_router(account.router)
    # Role-gated areas: each router requires its role (app.auth.require_role).
    for area in (parents, sitters, admin):
        app.include_router(area.router)
    return app


app = create_app()
