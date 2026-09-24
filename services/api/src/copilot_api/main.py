from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from copilot_api import health
from copilot_api.config import get_settings
from copilot_api.logging import configure_logging
from copilot_api.middleware import RequestIdMiddleware


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(title="Seller Support Copilot API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET"],
        allow_headers=["X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    # Added last so it runs outermost and every response, including CORS preflights, gets an ID.
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health.router)
    return app


app = create_app()
