"""Health-check endpoint."""

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    """Return process readiness metadata without exposing credentials."""

    settings = get_settings()
    return {
        "status": "ok",
        "application": settings.app_name,
        "environment": settings.app_env,
        "tenant": settings.tenant_code,
        "revision": settings.app_revision,
    }

