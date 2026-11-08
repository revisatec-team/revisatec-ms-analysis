"""Service for group reports and checklist milestones."""
from fastapi import HTTPException
from app.db.cosmos import get_database, REPORT_CHECKLIST_COLLECTION
from app.models.report import Report, ChecklistItem
from app.services.analysis import get_course_id_for_group, get_course_settings_or_404


def get_group_report(group_id: int) -> Report:
    """Retrieve group report checklist, raising 404 if not found."""
    course_id = get_course_id_for_group(group_id)
    get_course_settings_or_404(course_id)

    db = get_database()
    raw_docs = list(db[REPORT_CHECKLIST_COLLECTION].find({"groupId": group_id}))

    if not raw_docs:
        raise HTTPException(
            status_code=404,
            detail=f"Reporte no encontrado para el grupo {group_id}",
        )

    # Sort in Python by date ascending
    sorted_docs = sorted(raw_docs, key=lambda doc: doc.get("date", 0))

    items = [
        ChecklistItem(
            name=str(doc.get("name", "")),
            date=int(doc.get("date", 0)),
            status=str(doc.get("status", "pendiente")),
        )
        for doc in sorted_docs
    ]

    return Report(checklist=items)
