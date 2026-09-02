"""FastAPI application entry point."""

from fastapi import FastAPI

from app.api.exotel_webhook import router as exotel_webhook_router
from app.api.health import router as health_router
from app.config import get_settings


def create_app() -> FastAPI:
    """Create the isolated Marine chatbot API."""

    settings = get_settings()
    application = FastAPI(title=settings.app_name, debug=settings.debug)
    application.include_router(health_router)
    application.include_router(exotel_webhook_router)
    return application


app = create_app()
