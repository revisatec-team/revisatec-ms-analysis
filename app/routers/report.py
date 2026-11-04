"""Routers for group reports."""
from fastapi import APIRouter, Path
from app.models.report import Report
from app.services import report as service

router = APIRouter(prefix="/groups/{id}", tags=["Reports"])


@router.get("/report", response_model=Report, operation_id="getGroupReport")
def get_group_report(id: int = Path(..., description="ID del grupo")):
    """Reporte del grupo."""
    return service.get_group_report(group_id=id)
