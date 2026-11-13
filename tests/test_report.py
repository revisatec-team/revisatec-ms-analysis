"""Tests for group report endpoint."""
from fastapi.testclient import TestClient
from app.db.cosmos import (
    COURSE_SETTINGS_COLLECTION,
    REPORT_CHECKLIST_COLLECTION,
    FEEDBACK_COLLECTION,
)
from scripts.seed import seed_database


def test_get_report_404_no_rubric(client: TestClient, mock_db):
    """GET /groups/{id}/report returns 404 when course has no rubric."""
    mock_db[FEEDBACK_COLLECTION].insert_one(
        {"groupId": 888, "courseId": 888, "groupName": "Grupo 888"}
    )
    res = client.get("/groups/888/report")
    assert res.status_code == 404
    assert res.json()["error"] == "El curso 888 no tiene una rúbrica configurada"


def test_get_report_404_unconfigured_group(client: TestClient):
    """GET /groups/{id}/report returns 404 when group is not configured in MS2."""
    res = client.get("/groups/999/report")
    assert res.status_code == 404
    assert res.json() == {"error": "El grupo 999 no está configurado en MS2"}


def test_get_report_404_no_checklist(client: TestClient, mock_db):
    """GET /groups/{id}/report returns 404 when group has no checklist entries."""
    seed_database(mock_db)
    mock_db[FEEDBACK_COLLECTION].insert_one(
        {"groupId": 99, "courseId": 1, "groupName": "Grupo 99"}
    )

    # Group 99 has no checklist
    res = client.get("/groups/99/report")
    assert res.status_code == 404
    assert "error" in res.json()


def test_get_report_success(client: TestClient, mock_db):
    """GET /groups/{id}/report returns 200 with checklist items for seeded group."""
    seed_database(mock_db)

    res = client.get("/groups/1/report")
    assert res.status_code == 200
    data = res.json()
    assert "checklist" in data
    assert len(data["checklist"]) == 3

    for item in data["checklist"]:
        assert "name" in item
        assert "date" in item
        assert item["date"] > 1e11
        assert item["status"] in ("completado", "pendiente")
