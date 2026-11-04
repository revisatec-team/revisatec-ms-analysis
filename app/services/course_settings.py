"""Service logic for course settings (rubric, instructions, scraping-config)."""
import time
from typing import Optional
from fastapi import HTTPException
from app.db.cosmos import get_database, COURSE_SETTINGS_COLLECTION
from app.models.course_settings import (
    Rubric,
    Instructions,
    ScrapingConfig,
    ScrapingFrequency,
)


def calculate_next_run_at(frequency: ScrapingFrequency) -> int:
    """Calculate nextRunAt timestamp in Epoch milliseconds based on frequency."""
    now_ms = int(time.time() * 1000)
    if frequency == ScrapingFrequency.HOURLY:
        return now_ms + (3600 * 1000)
    elif frequency == ScrapingFrequency.DAILY:
        return now_ms + (24 * 3600 * 1000)
    elif frequency == ScrapingFrequency.WEEKLY:
        return now_ms + (7 * 24 * 3600 * 1000)
    return now_ms + (24 * 3600 * 1000)


def get_rubric(course_id: int) -> Rubric:
    """Retrieve rubric for courseId, raising 404 if course document or rubric is missing."""
    db = get_database()
    doc = db[COURSE_SETTINGS_COLLECTION].find_one({"courseId": course_id})
    if not doc or not doc.get("rubric"):
        raise HTTPException(status_code=404, detail=f"Rúbrica no encontrada para el curso {course_id}")
    return Rubric(**doc["rubric"])


def update_rubric(course_id: int, rubric_input: Rubric) -> Rubric:
    """Upsert rubric for courseId, preserving fileName and interpretationStatus if not provided."""
    db = get_database()
    doc = db[COURSE_SETTINGS_COLLECTION].find_one({"courseId": course_id})
    existing_rubric = (doc.get("rubric") or {}) if doc else {}

    file_name = rubric_input.fileName if rubric_input.fileName is not None else existing_rubric.get("fileName")
    status = rubric_input.interpretationStatus if rubric_input.interpretationStatus is not None else existing_rubric.get("interpretationStatus")

    rubric_data = {
        "criteria": [c.model_dump() for c in rubric_input.criteria],
        "fileName": file_name,
        "interpretationStatus": status,
    }

    db[COURSE_SETTINGS_COLLECTION].update_one(
        {"courseId": course_id},
        {"$set": {"courseId": course_id, "rubric": rubric_data}},
        upsert=True,
    )
    return Rubric(**rubric_data)


def get_instructions(course_id: int) -> Instructions:
    """Retrieve instructions for courseId, raising 404 if missing."""
    db = get_database()
    doc = db[COURSE_SETTINGS_COLLECTION].find_one({"courseId": course_id})
    if not doc or not doc.get("instructions"):
        raise HTTPException(status_code=404, detail=f"Indicaciones no encontradas para el curso {course_id}")
    return Instructions(**doc["instructions"])


def update_instructions(course_id: int, instructions_input: Instructions) -> Instructions:
    """Upsert instructions for courseId."""
    db = get_database()
    instructions_data = {"text": instructions_input.text}

    db[COURSE_SETTINGS_COLLECTION].update_one(
        {"courseId": course_id},
        {"$set": {"courseId": course_id, "instructions": instructions_data}},
        upsert=True,
    )
    return Instructions(**instructions_data)


def get_scraping_config(course_id: int) -> ScrapingConfig:
    """Retrieve scraping configuration for courseId, raising 404 if missing."""
    db = get_database()
    doc = db[COURSE_SETTINGS_COLLECTION].find_one({"courseId": course_id})
    if not doc or not doc.get("scrapingConfig"):
        raise HTTPException(status_code=404, detail=f"Configuración de scraping no encontrada para el curso {course_id}")
    return ScrapingConfig(**doc["scrapingConfig"])


def update_scraping_config(course_id: int, config_input: ScrapingConfig) -> ScrapingConfig:
    """Upsert scraping configuration for courseId, recalculating nextRunAt."""
    db = get_database()
    next_run_at = calculate_next_run_at(config_input.frequency)

    config_data = {
        "frequency": config_input.frequency.value,
        "minReviewers": config_input.minReviewers,
        "nextRunAt": next_run_at,
    }

    db[COURSE_SETTINGS_COLLECTION].update_one(
        {"courseId": course_id},
        {"$set": {"courseId": course_id, "scrapingConfig": config_data}},
        upsert=True,
    )
    return ScrapingConfig(**config_data)
