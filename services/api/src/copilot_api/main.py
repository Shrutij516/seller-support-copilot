from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from copilot_api import db, health
from copilot_api.auth import JWKSCache
from copilot_api.config import get_settings
from copilot_api.dynamo.chat_repository import ChatRepository
from copilot_api.dynamo.client import create_dynamodb_client
from copilot_api.errors import register_exception_handlers
from copilot_api.logging import configure_logging
from copilot_api.middleware import RequestIdMiddleware
from copilot_api.routers import admin, cases, chat, listings, me, orders


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await app.state.db_engine.dispose()
    await app.state.jwks_cache.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(title="Seller Support Copilot API", version="0.1.0", lifespan=lifespan)

    engine = db.create_engine(settings)
    app.state.db_engine = engine
    app.state.db_session_factory = db.create_session_factory(engine)
    app.state.jwks_cache = JWKSCache(settings.cognito_jwks_url)
    app.state.chat_repo = ChatRepository(create_dynamodb_client(settings))

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["X-Request-ID", "Authorization", "Content-Type"],
        expose_headers=["X-Request-ID"],
    )
    # Added last so it runs outermost and every response, including CORS preflights, gets an ID.
    app.add_middleware(RequestIdMiddleware)

    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(me.router)
    app.include_router(listings.router)
    app.include_router(orders.router)
    app.include_router(cases.router)
    app.include_router(chat.router)
    app.include_router(admin.router)
    return app


app = create_app()
