from fastapi import APIRouter

from app.config import API_TITLE, API_VERSION, settings

router = APIRouter(tags=["Healthcheck"])


@router.get("/", summary="Healthcheck")
def healthcheck():
    """Public liveness probe with API name and version."""
    response = {
        "status": "ok",
        "name": API_TITLE,
        "version": API_VERSION,
        "env": settings.env,
    }
    if settings.env.startswith("dev"):
        response["docs_url"] = "/docs"

    return response
