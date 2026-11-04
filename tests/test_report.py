"""Tests for group report endpoint."""
from fastapi.testclient import TestClient
from app.db.cosmos import (
    COURSE_SETTINGS_COLLECTION,
    REPORT_CHECKLIST_COLLECTION,
)
from scripts.seed import seed_database


def test_get_report_404_no_rubric(client: TestClient):
    """GET /groups/{id}/report returns 404 when course has no rubric."""
    res = client.get("/groups/999/report")
    assert res.status_code == 404
    assert "error" in res.json()


def test_get_report_404_no_checklist(client: TestClient, mock_db):
    """GET /groups/{id}/report returns 404 when group has no checklist entries."""
    seed_database(mock_db)

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
