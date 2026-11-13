"""Service for computing group analysis, progress summary, criteria, and issue detection."""
import logging
import re
import time
import uuid
from typing import Dict, List, Tuple
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from app.db.cosmos import (
    get_database,
    COURSE_SETTINGS_COLLECTION,
    GITHUB_EVENTS_COLLECTION,
    FEEDBACK_COLLECTION,
    ISSUES_COLLECTION,
)
from app.models.analysis import (
    Analysis,
    CriterionScore,
    Evidence,
    ProgressSummary,
    ProgressItem,
    CriterionCompliance,
    GroupCriteriaResponse,
    Issue,
)
from app.models.common import PaginatedResponse
from app.services.queue_publisher import get_publisher, create_queue_event

logger = logging.getLogger(__name__)

ISSUE_KEYWORDS_PATTERN = re.compile(r"\b(test|prueba|wip|asdf|tmp)\b", re.IGNORECASE)


def get_course_id_for_group(group_id: int) -> int:
    """Resolve the courseId for a group from FEEDBACK_COLLECTION; raises 404 if not found or missing courseId."""
    db = get_database()
    fb = db[FEEDBACK_COLLECTION].find_one({"groupId": group_id})
    if not fb or not fb.get("courseId"):
        raise HTTPException(
            status_code=404,
            detail=f"El grupo {group_id} no está configurado en MS2",
        )
    return int(fb["courseId"])


def get_group_name(group_id: int) -> str:
    """Nombre del grupo guardado en feedback (sembrado desde MS1); por defecto 'Grupo {id}'."""
    db = get_database()
    fb = db[FEEDBACK_COLLECTION].find_one({"groupId": group_id})
    if fb and fb.get("groupName"):
        return str(fb["groupName"])
    return f"Grupo {group_id}"


def get_course_settings_or_404(course_id: int) -> dict:
    """Retrieve course settings ensuring a rubric is configured, raising 404 otherwise."""
    db = get_database()
    course = db[COURSE_SETTINGS_COLLECTION].find_one({"courseId": course_id})
    if not course or not course.get("rubric") or not course["rubric"].get("criteria"):
        raise HTTPException(
            status_code=404,
            detail=f"El curso {course_id} no tiene una rúbrica configurada",
        )
    return course


def calculate_group_metrics(group_id: int, min_reviewers: int = 1) -> Tuple[float, float, float]:
    """Calculate the three core metrics for a group: (Código, Revisiones, Consistencia)."""
    db = get_database()
    events = list(db[GITHUB_EVENTS_COLLECTION].find({"groupId": group_id}))

    commits = [e for e in events if e.get("type") == "commit"]
    prs = [e for e in events if e.get("type") == "pr"]

    # 1. Código: min(100, commits / 20 * 100)
    commits_count = len(commits)
    metric_codigo = min(100.0, (commits_count / 20.0) * 100.0)

    # 2. Revisiones: % de PRs con >= minReviewers revisores (0 sin PRs)
    if len(prs) == 0:
        metric_revisiones = 0.0
    else:
        prs_with_min = [p for p in prs if len(p.get("reviewers", [])) >= min_reviewers]
        metric_revisiones = (len(prs_with_min) / float(len(prs))) * 100.0

    # 3. Consistencia: % de las últimas 4 semanas con al menos un commit
    now_ms = int(time.time() * 1000)
    day_ms = 86_400_000
    weeks_with_commits = 0
    for i in range(4):
        # Week 0 is most recent (now - 7d to now), week 3 is (now - 28d to now - 21d)
        start_ms = now_ms - ((i + 1) * 7 * day_ms)
        end_ms = now_ms - (i * 7 * day_ms)
        if any(start_ms <= c.get("createdAt", 0) <= end_ms for c in commits):
            weeks_with_commits += 1

    metric_consistencia = (weeks_with_commits / 4.0) * 100.0

    return metric_codigo, metric_revisiones, metric_consistencia


def compute_criteria_scores(
    rubric: dict,
    metric_codigo: float,
    metric_revisiones: float,
    metric_consistencia: float,
) -> List[CriterionScore]:
    """Associate criteria with metrics and calculate scores and levels."""
    scores: List[CriterionScore] = []
    for criterion in rubric.get("criteria", []):
        name = criterion["name"]
        weight = float(criterion["weight"])
        name_lower = name.lower()

        if "revis" in name_lower:
            percent_val = metric_revisiones
        elif "consist" in name_lower or "constan" in name_lower:
            percent_val = metric_consistencia
        else:
            percent_val = metric_codigo

        rounded_percent = int(round(percent_val))
        # Puntaje: round(peso * porcentaje / 100) con tope en el peso
        score = min(weight, round((weight * percent_val) / 100.0))

        if rounded_percent >= 80:
            level = "Bueno"
            level_type = "success"
        elif rounded_percent >= 60:
            level = "En progreso"
            level_type = "warning"
        else:
            level = "Bajo"
            level_type = "alert"

        scores.append(
            CriterionScore(
                name=name,
                score=float(score),
                max=weight,
                percent=rounded_percent,
                level=level,
                type=level_type,
            )
        )
    return scores


def get_group_analysis(group_id: int) -> Analysis:
    """Compute and return full analysis for a group."""
    course_id = get_course_id_for_group(group_id)
    course = get_course_settings_or_404(course_id)
    rubric = course["rubric"]
    scraping_config = course.get("scrapingConfig") or {}
    min_reviewers = scraping_config.get("minReviewers", 1)

    metric_codigo, metric_revisiones, metric_consistencia = calculate_group_metrics(
        group_id=group_id,
        min_reviewers=min_reviewers,
    )

    criteria_scores = compute_criteria_scores(
        rubric=rubric,
        metric_codigo=metric_codigo,
        metric_revisiones=metric_revisiones,
        metric_consistencia=metric_consistencia,
    )

    total_score = sum(c.score for c in criteria_scores)
    progress = int(round((metric_codigo + metric_revisiones + metric_consistencia) / 3.0))

    # Evidence: 10 most recent events
    db = get_database()
    recent_events_cursor = (
        db[GITHUB_EVENTS_COLLECTION]
        .find({"groupId": group_id})
        .sort("createdAt", -1)
        .limit(10)
    )

    evidence_list = []
    for ev in recent_events_cursor:
        first_reviewer = ev["reviewers"][0] if ev.get("reviewers") else None
        evidence_list.append(
            Evidence(
                id=str(ev.get("id")),
                type=str(ev.get("type", "commit")),
                text=str(ev.get("message", "")),
                author=str(ev.get("author", "")),
                reviewer=first_reviewer,
                when=int(ev.get("createdAt", 0)),
            )
        )

    return Analysis(
        score=float(total_score),
        progress=progress,
        criteria=criteria_scores,
        evidence=evidence_list,
    )


def get_progress_summary(group_id: int) -> ProgressSummary:
    """Compute and return progress summary for a group."""
    analysis = get_group_analysis(group_id)

    items: List[ProgressItem] = []
    for c in analysis.criteria:
        crit_id = re.sub(r"\W+", "_", c.name.lower()).strip("_")
        if c.percent >= 80:
            status = "on_track"
            note = f"Criterio '{c.name}' con cumplimiento adecuado ({c.percent}%)"
        elif c.percent >= 60:
            status = "at_risk"
            note = f"Criterio '{c.name}' en progreso ({c.percent}%)"
        else:
            status = "delayed"
            note = f"Criterio '{c.name}' con bajo cumplimiento ({c.percent}%)"

        items.append(
            ProgressItem(
                criterionId=crit_id,
                name=c.name,
                status=status,
                note=note,
            )
        )

    return ProgressSummary(
        groupId=group_id,
        overall=analysis.progress,
        items=items,
        generatedAt=int(time.time() * 1000),
    )


def get_group_criteria(group_id: int) -> GroupCriteriaResponse:
    """Compute and return criteria compliance for a group."""
    analysis = get_group_analysis(group_id)

    items: List[CriterionCompliance] = []
    for c in analysis.criteria:
        crit_id = re.sub(r"\W+", "_", c.name.lower()).strip("_")
        if c.percent >= 80:
            level = "met"
        elif c.percent >= 60:
            level = "partial"
        else:
            level = "not_met"

        items.append(
            CriterionCompliance(
                criterionId=crit_id,
                name=c.name,
                level=level,
                score=c.score,
            )
        )

    return GroupCriteriaResponse(groupId=group_id, items=items)


def detect_and_list_issues(
    group_id: int,
    page: int = 1,
    page_size: int = 10,
) -> PaginatedResponse[Issue]:
    """Scan group commits for issues, publish new ones, and return paginated issues."""
    course_id = get_course_id_for_group(group_id)
    # Validate course has rubric
    get_course_settings_or_404(course_id)

    db = get_database()
    commits = list(
        db[GITHUB_EVENTS_COLLECTION].find({"groupId": group_id, "type": "commit"})
    )

    publisher = get_publisher()

    # Detect issues idempotently by sourceEventId
    for commit in commits:
        msg = commit.get("message", "")
        if ISSUE_KEYWORDS_PATTERN.search(msg):
            source_id = str(commit.get("id"))
            existing = db[ISSUES_COLLECTION].find_one({"sourceEventId": source_id})
            if not existing:
                issue_id = str(uuid.uuid4().hex[:8])
                new_issue = {
                    "id": issue_id,
                    "groupId": group_id,
                    "groupName": get_group_name(group_id),
                    "type": "Commits de prueba",
                    "description": msg,
                    "date": int(commit.get("createdAt", time.time() * 1000)),
                    "status": "Sin resolver",
                    "sourceEventId": source_id,
                }
                try:
                    db[ISSUES_COLLECTION].insert_one(new_issue)
                except DuplicateKeyError:
                    continue

                # Emit queue event
                queue_event = create_queue_event(
                    event_type="ISSUE_DETECTED",
                    course_id=course_id,
                    group_id=group_id,
                    title="Inconveniente detectado",
                    message=f"Se detectó un commit de prueba en {get_group_name(group_id)}: '{msg}'",
                )
                try:
                    publisher.publish(queue_event)
                except Exception as e:
                    logger.error(f"Error publishing ISSUE_DETECTED event: {e}")

    # Paginate issues
    total_records = db[ISSUES_COLLECTION].count_documents({"groupId": group_id})
    skip = (page - 1) * page_size
    cursor = (
        db[ISSUES_COLLECTION]
        .find({"groupId": group_id})
        .sort("date", -1)
        .skip(skip)
        .limit(page_size)
    )

    items = []
    for doc in cursor:
        items.append(
            Issue(
                id=str(doc.get("id")),
                groupId=int(doc.get("groupId")),
                groupName=get_group_name(group_id),
                type=str(doc.get("type", "Commits de prueba")),
                description=str(doc.get("description", "")),
                date=int(doc.get("date", 0)),
                status=str(doc.get("status", "Sin resolver")),
            )
        )

    return PaginatedResponse[Issue](
        totalRecords=total_records,
        page=page,
        pageSize=page_size,
        items=items,
    )