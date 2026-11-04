"""Routers for group analysis, progress summary, criteria, and issues."""
from fastapi import APIRouter, Path, Query
from app.models.analysis import (
    Analysis,
    ProgressSummary,
    GroupCriteriaResponse,
    Issue,
)
from app.models.common import PaginatedResponse
from app.services import analysis as service

router = APIRouter(prefix="/groups/{id}", tags=["Group analysis"])


@router.get("/analysis", response_model=Analysis, operation_id="getGroupAnalysis")
def get_group_analysis(id: int = Path(..., description="ID del grupo")):
    """Puntaje y evidencia del grupo."""
    return service.get_group_analysis(group_id=id)


@router.get(
    "/progress-summary",
    response_model=ProgressSummary,
    operation_id="getProgressSummary",
)
def get_progress_summary(id: int = Path(..., description="ID del grupo")):
    """Estado del avance por criterio."""
    return service.get_progress_summary(group_id=id)


@router.get(
    "/criteria",
    response_model=GroupCriteriaResponse,
    operation_id="getGroupCriteria",
)
def get_group_criteria(id: int = Path(..., description="ID del grupo")):
    """Nivel de cumplimiento por criterio."""
    return service.get_group_criteria(group_id=id)


@router.get(
    "/issues",
    response_model=PaginatedResponse[Issue],
    operation_id="listGroupIssues",
)
def list_group_issues(
    id: int = Path(..., description="ID del grupo"),
    page: int = Query(1, ge=1, description="Número de página"),
    pageSize: int = Query(10, ge=1, le=100, description="Tamaño de página"),
):
    """Inconvenientes detectados (paginado)."""
    return service.detect_and_list_issues(group_id=id, page=page, page_size=pageSize)
