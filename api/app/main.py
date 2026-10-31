import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.errors import register_error_handlers
from app.routers import health
from app.settings import Settings, get_settings


def init_sentry(settings: Settings) -> bool:
    """Turn on Sentry only when SENTRY_DSN is set. Returns whether it was turned on."""
    if not settings.sentry_dsn:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        send_default_pii=False,  # no IPs, cookies or request bodies about parents, children or sitters
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
