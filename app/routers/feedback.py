"""Routers for feedback, publishing, and direct reviews."""
from fastapi import APIRouter, Path, Query, status
from app.models.common import PaginatedResponse
from app.models.feedback import Feedback, FeedbackInput, DirectReview, DirectReviewInput
from app.services import feedback as service

router = APIRouter(prefix="/groups/{id}", tags=["Feedback"])


@router.get("/feedback", response_model=Feedback, operation_id="getFeedback")
def get_feedback(id: int = Path(..., description="ID del grupo")):
    """Obtener retroalimentación (versión IA y versión del profesor)."""
    return service.get_or_create_feedback(group_id=id)


@router.put("/feedback", response_model=Feedback, operation_id="updateFeedback")
def update_feedback(
    feedback: FeedbackInput,
    id: int = Path(..., description="ID del grupo"),
):
    """Guardar la versión editada por el profesor."""
    return service.update_feedback(group_id=id, feedback_input=feedback)


@router.post("/feedback/publish", response_model=Feedback, operation_id="publishFeedback")
def publish_feedback(id: int = Path(..., description="ID del grupo")):
    """Publicar la retroalimentación al estudiante y emitir a la cola."""
    return service.publish_feedback(group_id=id)


@router.get(
    "/direct-reviews",
    response_model=PaginatedResponse[DirectReview],
    operation_id="listDirectReviews",
)
def list_direct_reviews(
    id: int = Path(..., description="ID del grupo"),
    page: int = Query(1, ge=1, description="Número de página"),
    pageSize: int = Query(10, ge=1, le=100, description="Tamaño de página"),
):
    """Listar revisiones directas del grupo (paginado)."""
    return service.list_direct_reviews(group_id=id, page=page, page_size=pageSize)


@router.post(
    "/direct-reviews",
    response_model=DirectReview,
    status_code=status.HTTP_201_CREATED,
    operation_id="createDirectReview",
)
def create_direct_review(
    review: DirectReviewInput,
    id: int = Path(..., description="ID del grupo"),
):
    """Crear revisión directa fuera del flujo normal."""
    return service.create_direct_review(group_id=id, review_input=review)
