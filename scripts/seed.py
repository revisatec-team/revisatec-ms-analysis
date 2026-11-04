"""Database seed script for RevisaTEC MS2 Analysis.
Idempotent upsert of course_settings, github_events, and report_checklist.
"""
import time
from typing import Optional
from pymongo.database import Database

from app.db.cosmos import (
    get_database,
    COURSE_SETTINGS_COLLECTION,
    GITHUB_EVENTS_COLLECTION,
    REPORT_CHECKLIST_COLLECTION,
    init_indexes,
)


def seed_database(db: Optional[Database] = None) -> dict:
    """Seed course_settings, github_events, and report_checklist idempotently."""
    if db is None:
        db = get_database()

    init_indexes(db)

    now_ms = int(time.time() * 1000)
    day_ms = 86_400_000

    # 1. Course settings for course 1
    course_settings_1 = {
        "courseId": 1,
        "rubric": {
            "fileName": "rubrica.pdf",
            "interpretationStatus": "Interpretada por IA",
            "criteria": [
                {"name": "Calidad de código", "weight": 40.0},
                {"name": "Revisiones entre pares", "weight": 40.0},
                {"name": "Consistencia", "weight": 20.0},
            ],
        },
        "instructions": {
            "text": "Priorizar la revisión entre pares.",
        },
        "scrapingConfig": {
            "frequency": "daily",
            "minReviewers": 1,
            "nextRunAt": now_ms + day_ms,
        },
    }

    db[COURSE_SETTINGS_COLLECTION].update_one(
        {"courseId": 1},
        {"$set": course_settings_1},
        upsert=True,
    )

    # 2. github_events for groups 1, 2, 3
    # Spread over the last 4 weeks (28 days)
    events = [
        # Group 1 events (Active group, good consistency, PRs with reviewers and tests)
        {
            "id": "g1_c01",
            "groupId": 1,
            "type": "commit",
            "author": "estudiante1",
            "reviewers": [],
            "message": "feat: inicializar arquitectura limpia",
            "createdAt": now_ms - (26 * day_ms),
        },
        {
            "id": "g1_c02",
            "groupId": 1,
            "type": "commit",
            "author": "estudiante2",
            "reviewers": [],
            "message": "feat: configuracion de base de datos",
            "createdAt": now_ms - (20 * day_ms),
        },
        {
            "id": "g1_pr01",
            "groupId": 1,
            "type": "pr",
            "author": "estudiante1",
            "reviewers": ["estudiante2"],
            "message": "PR #1: Modulo de configuracion y cosmos db",
            "createdAt": now_ms - (19 * day_ms),
        },
        {
            "id": "g1_c03",
            "groupId": 1,
            "type": "commit",
            "author": "estudiante1",
            "reviewers": [],
            "message": "wip: prueba temporal de conexion",
            "createdAt": now_ms - (14 * day_ms),
        },
        {
            "id": "g1_c04",
            "groupId": 1,
            "type": "commit",
            "author": "estudiante3",
            "reviewers": [],
            "message": "feat: endpoints de administracion",
            "createdAt": now_ms - (12 * day_ms),
        },
        {
            "id": "g1_pr02",
            "groupId": 1,
            "type": "pr",
            "author": "estudiante3",
            "reviewers": ["estudiante1", "estudiante2"],
            "message": "PR #2: Integracion de routers y validaciones",
            "createdAt": now_ms - (10 * day_ms),
        },
        {
            "id": "g1_c05",
            "groupId": 1,
            "type": "commit",
            "author": "estudiante2",
            "reviewers": [],
            "message": "fix: ajuste en formato de fechas epoch",
            "createdAt": now_ms - (5 * day_ms),
        },
        {
            "id": "g1_c06",
            "groupId": 1,
            "type": "commit",
            "author": "estudiante1",
            "reviewers": [],
            "message": "test: verificacion de endpoints",
            "createdAt": now_ms - (2 * day_ms),
        },
        {
            "id": "g1_pr03",
            "groupId": 1,
            "type": "pr",
            "author": "estudiante2",
            "reviewers": [],
            "message": "PR #3: Hotfix sin revisores asignados",
            "createdAt": now_ms - (1 * day_ms),
        },

        # Group 2 events (Moderate group, some wip commits, PR without reviewers)
        {
            "id": "g2_c01",
            "groupId": 2,
            "type": "commit",
            "author": "estudiante4",
            "reviewers": [],
            "message": "feat: esqueleto del proyecto",
            "createdAt": now_ms - (22 * day_ms),
        },
        {
            "id": "g2_c02",
            "groupId": 2,
            "type": "commit",
            "author": "estudiante5",
            "reviewers": [],
            "message": "wip avance preliminar",
            "createdAt": now_ms - (15 * day_ms),
        },
        {
            "id": "g2_pr01",
            "groupId": 2,
            "type": "pr",
            "author": "estudiante4",
            "reviewers": [],
            "message": "PR #1: Avance entrega 1",
            "createdAt": now_ms - (13 * day_ms),
        },
        {
            "id": "g2_c03",
            "groupId": 2,
            "type": "commit",
            "author": "estudiante5",
            "reviewers": [],
            "message": "prueba rápida en local",
            "createdAt": now_ms - (4 * day_ms),
        },

        # Group 3 events (Low activity group)
        {
            "id": "g3_c01",
            "groupId": 3,
            "type": "commit",
            "author": "estudiante6",
            "reviewers": [],
            "message": "init repo",
            "createdAt": now_ms - (25 * day_ms),
        },
        {
            "id": "g3_c02",
            "groupId": 3,
            "type": "commit",
            "author": "estudiante6",
            "reviewers": [],
            "message": "test commit de prueba inicial",
            "createdAt": now_ms - (8 * day_ms),
        },
        {
            "id": "g3_pr01",
            "groupId": 3,
            "type": "pr",
            "author": "estudiante6",
            "reviewers": ["estudiante7"],
            "message": "PR #1: Estructura inicial",
            "createdAt": now_ms - (7 * day_ms),
        },
    ]

    for ev in events:
        db[GITHUB_EVENTS_COLLECTION].update_one(
            {"id": ev["id"]},
            {"$set": ev},
            upsert=True,
        )

    # 3. report_checklist for groups 1, 2, 3
    checklist_items = [
        # Group 1
        {
            "groupId": 1,
            "name": "Entrega 1: Especificación y Requisitos",
            "date": now_ms - (20 * day_ms),
            "status": "completado",
        },
        {
            "groupId": 1,
            "name": "Entrega 2: Prototipo",
            "date": now_ms + (5 * day_ms),
            "status": "pendiente",
        },
        {
            "groupId": 1,
            "name": "Entrega 3: Presentación Final",
            "date": now_ms + (25 * day_ms),
            "status": "pendiente",
        },
        # Group 2
        {
            "groupId": 2,
            "name": "Entrega 1: Especificación y Requisitos",
            "date": now_ms - (18 * day_ms),
            "status": "completado",
        },
        {
            "groupId": 2,
            "name": "Entrega 2: Prototipo",
            "date": now_ms + (5 * day_ms),
            "status": "pendiente",
        },
        # Group 3
        {
            "groupId": 3,
            "name": "Entrega 1: Especificación y Requisitos",
            "date": now_ms - (10 * day_ms),
            "status": "pendiente",
        },
    ]

    for item in checklist_items:
        db[REPORT_CHECKLIST_COLLECTION].update_one(
            {"groupId": item["groupId"], "name": item["name"]},
            {"$set": item},
            upsert=True,
        )

    course_settings_count = db[COURSE_SETTINGS_COLLECTION].count_documents({})
    github_events_count = db[GITHUB_EVENTS_COLLECTION].count_documents({})
    report_checklist_count = db[REPORT_CHECKLIST_COLLECTION].count_documents({})

    return {
        "course_settings_count": course_settings_count,
        "github_events_count": github_events_count,
        "report_checklist_count": report_checklist_count,
        "total_events": len(events),
        "total_checklist": len(checklist_items),
    }


if __name__ == "__main__":
    result = seed_database()
    print("Seed executed successfully:", result)
