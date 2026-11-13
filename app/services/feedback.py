"""Service for feedback management, queue notifications, and direct reviews."""
import logging
import time
import uuid
from fastapi import HTTPException

from app.db.cosmos import (
    get_database,
    FEEDBACK_COLLECTION,
    DIRECT_REVIEWS_COLLECTION,
)
from app.models.common import PaginatedResponse
from app.models.feedback import Feedback, FeedbackInput, DirectReview, DirectReviewInput
from app.services.analysis import (
    get_course_id_for_group,
    get_course_settings_or_404,
    get_group_analysis,
    get_group_name,
)
from app.services.queue_publisher import get_publisher, create_queue_event

logger = logging.getLogger(__name__)


def _generate_ai_feedback(analysis) -> str:
    criteria = analysis.criteria
    if criteria:
        sorted_criteria = sorted(criteria, key=lambda c: c.percent, reverse=True)
        best = sorted_criteria[0]
        worst = sorted_criteria[-1]
        if len(criteria) == 1 or best.percent == worst.percent:
            return (
                f"El grupo obtiene {int(round(analysis.score))}/100. "
                f"Rendimiento parejo en todos los criterios ({best.percent}%)."
            )
        return (
            f"El grupo obtiene {int(round(analysis.score))}/100. "
            f"Fortaleza: {best.name} ({best.percent}%). "
            f"A mejorar: {worst.name} ({worst.percent}%)."
        )
    return f"El grupo obtiene {int(round(analysis.score))}/100."


def get_or_create_feedback(group_id: int) -> Feedback:
    """Retrieve existing feedback (frozen if published, recalculated if draft) or generate an AI draft."""
    course_id = get_course_id_for_group(group_id)
    get_course_settings_or_404(course_id)

    db = get_database()
    doc = db[FEEDBACK_COLLECTION].find_one({"groupId": group_id})

    # Si está published, no recalcular nada
    if doc and doc.get("status") == "published":
        return Feedback(
            groupName=doc.get("groupName") or get_group_name(group_id),
            deliveryTitle=doc.get("deliveryTitle", "Entrega actual"),
            score=doc.get("score"),
            ai=doc.get("ai"),
            professor=doc.get("professor", ""),
            status="published",
            publishedAt=doc.get("publishedAt"),
            notified=doc.get("notified"),
        )

    # Si no existe o su status es "draft", recalcular score y ai
    analysis = get_group_analysis(group_id)
    ai_text = _generate_ai_feedback(analysis)
    now_ms = int(time.time() * 1000)

    group_name = doc.get("groupName") if doc and doc.get("groupName") else get_group_name(group_id)
    delivery_title = doc.get("deliveryTitle", "Entrega actual") if doc else "Entrega actual"
    professor = doc.get("professor", "") if doc else ""
    status = "draft"
    published_at = None

    draft_doc = {
        "groupId": group_id,
        "courseId": course_id,
        "groupName": group_name,
        "deliveryTitle": delivery_title,
        "score": float(analysis.score),
        "ai": ai_text,
        "professor": professor,
        "status": status,
        "updatedAt": now_ms,
        "publishedAt": published_at,
        "notified": doc.get("notified") if doc else None,
    }
    db[FEEDBACK_COLLECTION].update_one(
        {"groupId": group_id},
        {"$set": draft_doc},
        upsert=True,
    )

    return Feedback(
        groupName=draft_doc["groupName"],
        deliveryTitle=draft_doc["deliveryTitle"],
        score=draft_doc["score"],
        ai=draft_doc["ai"],
        professor=draft_doc["professor"],
        status=draft_doc["status"],
        publishedAt=draft_doc["publishedAt"],
        notified=draft_doc.get("notified"),
    )


def update_feedback(group_id: int, feedback_input: FeedbackInput) -> Feedback:
    """Update professor feedback, creating it with AI draft if not existing."""
    course_id = get_course_id_for_group(group_id)
    get_course_settings_or_404(course_id)

    db = get_database()
    doc = db[FEEDBACK_COLLECTION].find_one({"groupId": group_id})
    now_ms = int(time.time() * 1000)

    if doc and doc.get("status") == "published":
        raise HTTPException(
            status_code=409,
            detail="La retroalimentación ya fue publicada y no se puede editar",
        )

    if not doc or doc.get("ai") is None:
        analysis = get_group_analysis(group_id)
        ai_text = feedback_input.ai if feedback_input.ai is not None else _generate_ai_feedback(analysis)
        group_name = doc.get("groupName") if doc and doc.get("groupName") else get_group_name(group_id)
        delivery_title = doc.get("deliveryTitle", "Entrega actual") if doc else "Entrega actual"
        status = "draft"
        published_at = None

        draft_doc = {
            "groupId": group_id,
            "courseId": course_id,
            "groupName": group_name,
            "deliveryTitle": delivery_title,
            "score": float(analysis.score),
            "ai": ai_text,
            "professor": feedback_input.professor,
            "status": status,
            "updatedAt": now_ms,
            "publishedAt": published_at,
            "notified": doc.get("notified") if doc else None,
        }
        db[FEEDBACK_COLLECTION].update_one(
            {"groupId": group_id},
            {"$set": draft_doc},
            upsert=True,
        )
        doc = draft_doc
    else:
        update_data = {
            "professor": feedback_input.professor,
            "updatedAt": now_ms,
        }
        if feedback_input.ai is not None:
            update_data["ai"] = feedback_input.ai

        db[FEEDBACK_COLLECTION].update_one({"groupId": group_id}, {"$set": update_data})
        doc.update(update_data)

    return Feedback(
        groupName=doc.get("groupName") or get_group_name(group_id),
        deliveryTitle=doc.get("deliveryTitle", "Entrega actual"),
        score=doc.get("score"),
        ai=doc.get("ai"),
        professor=doc.get("professor", ""),
        status=doc.get("status", "draft"),
        publishedAt=doc.get("publishedAt"),
        notified=doc.get("notified"),
    )


def publish_feedback(group_id: int) -> Feedback:
    """Publish feedback and notify via queue."""
    course_id = get_course_id_for_group(group_id)
    get_course_settings_or_404(course_id)

    db = get_database()
    doc = db[FEEDBACK_COLLECTION].find_one({"groupId": group_id})
    if not doc or doc.get("ai") is None:
        raise HTTPException(
            status_code=404,
            detail=f"Retroalimentación no encontrada para el grupo {group_id}",
        )

    professor_text = (doc.get("professor") or "").strip()
    if not professor_text:
        raise HTTPException(
            status_code=400,
            detail="No se puede publicar: falta la retroalimentación del profesor",
        )

    now_ms = int(time.time() * 1000)
    result = db[FEEDBACK_COLLECTION].update_one(
        {"groupId": group_id, "status": {"$ne": "published"}},
        {"$set": {"status": "published", "publishedAt": now_ms, "updatedAt": now_ms}},
    )
    if result.matched_count == 0:
        raise HTTPException(
            status_code=409,
            detail="La retroalimentación ya fue publicada",
        )

    group_name = doc.get("groupName") or get_group_name(group_id)
    queue_event = create_queue_event(
        event_type="FEEDBACK_PUBLISHED",
        course_id=doc.get("courseId", course_id),
        group_id=group_id,
        title="Retroalimentación publicada",
        message=f"Se publicó la retroalimentación de {group_name}",
    )

    notified = True
    try:
        publisher = get_publisher()
        success = publisher.publish(queue_event)
        if not success:
            notified = False
            logger.error("Queue publisher failed to publish FEEDBACK_PUBLISHED event")
    except Exception as e:
        notified = False
        logger.error(f"Error publishing FEEDBACK_PUBLISHED event: {e}")

    # Persistir notified en base de datos
    db[FEEDBACK_COLLECTION].update_one(
        {"groupId": group_id},
        {"$set": {"notified": notified}},
    )

    return Feedback(
        groupName=group_name,
        deliveryTitle=doc.get("deliveryTitle", "Entrega actual"),
        score=doc.get("score"),
        ai=doc.get("ai"),
        professor=professor_text,
        status="published",
        publishedAt=now_ms,
        notified=notified,
    )


def create_direct_review(group_id: int, review_input: DirectReviewInput) -> DirectReview:
    """Create a new direct review for a group."""
    course_id = get_course_id_for_group(group_id)
    get_course_settings_or_404(course_id)

    db = get_database()
    review_id = uuid.uuid4().hex[:8]
    now_ms = int(time.time() * 1000)

    doc = {
        "id": review_id,
        "groupId": group_id,
        "date": now_ms,
        "note": review_input.note,
    }
    db[DIRECT_REVIEWS_COLLECTION].insert_one(doc)

    return DirectReview(
        id=review_id,
        date=now_ms,
        note=review_input.note,
    )


def list_direct_reviews(
    group_id: int,
    page: int = 1,
    page_size: int = 10,
) -> PaginatedResponse[DirectReview]:
    """List paginated direct reviews for a group."""
    course_id = get_course_id_for_group(group_id)
    get_course_settings_or_404(course_id)

    db = get_database()
    total_records = db[DIRECT_REVIEWS_COLLECTION].count_documents({"groupId": group_id})
    skip = (page - 1) * page_size
    cursor = (
        db[DIRECT_REVIEWS_COLLECTION]
        .find({"groupId": group_id})
        .sort("date", -1)
        .skip(skip)
        .limit(page_size)
    )

    items = [
        DirectReview(
            id=str(d.get("id")),
            date=int(d.get("date", 0)),
            note=str(d.get("note", "")),
        )
        for d in cursor
    ]

    return PaginatedResponse[DirectReview](
        totalRecords=total_records,
        page=page,
        pageSize=page_size,
        items=items,
    )
