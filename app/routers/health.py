"""Health check router for RevisaTEC MS2 Analysis."""
import time
from fastapi import APIRouter
from app.models.common import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
def get_health():
    """Return health status of the service."""
    return HealthResponse(
        status="ok",
        service="revisatec-ms-analysis",
        timestamp=int(time.time() * 1000),
    )
