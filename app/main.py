from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import get_settings
from app.ai.startup_validation import validate_openai_startup_configuration
from app.database.session import close_db, init_db
from app.routes.openai_diagnostic import router as openai_diagnostic_router
from app.routes.router import api_router
from app.utils.logging import configure_logging


@asynccontextmanager
async def lifespan(_: FastAPI):
    await validate_openai_startup_configuration()
    await init_db()
    yield
    await close_db()


def create_application() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    app.include_router(openai_diagnostic_router)
    return app


app = create_application()


