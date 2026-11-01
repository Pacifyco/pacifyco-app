import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.errors import register_error_handlers
from app.routers import health
from app.settings import Settings, get_settings

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


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    init_sentry(settings)

    app = FastAPI(title="Pacify API")
    app.dependency_overrides[get_settings] = lambda: settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    register_error_handlers(app)
    app.include_router(health.router)
    return app


app = create_app()
