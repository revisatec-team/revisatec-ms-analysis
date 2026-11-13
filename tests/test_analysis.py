"""Tests for group analysis, progress-summary, criteria, and issues detection."""
import time
from fastapi.testclient import TestClient
from app.db.cosmos import (
    COURSE_SETTINGS_COLLECTION,
    GITHUB_EVENTS_COLLECTION,
    ISSUES_COLLECTION,
    FEEDBACK_COLLECTION,
)
from scripts.seed import seed_database


def test_analysis_404_no_rubric(client: TestClient, mock_db):
    """GET /groups/{id}/analysis returns 404 when course has no rubric."""
    mock_db[FEEDBACK_COLLECTION].insert_one(
        {"groupId": 888, "courseId": 888, "groupName": "Grupo 888"}
    )
    response = client.get("/groups/888/analysis")
    assert response.status_code == 404
    assert response.json()["error"] == "El curso 888 no tiene una rúbrica configurada" 


def test_analysis_with_seed_data(client: TestClient, mock_db):
    """GET /groups/1/analysis calculates metrics, score, criteria, and evidence correctly."""
    seed_database(mock_db)

    response = client.get("/groups/1/analysis")
    assert response.status_code == 200
    data = response.json()

    assert "score" in data
    assert "progress" in data
    assert "criteria" in data
    assert "evidence" in data

    assert isinstance(data["score"], (int, float))
    assert 0 <= data["progress"] <= 100
    assert len(data["criteria"]) == 3

    # Check criteria structure and rules
    for crit in data["criteria"]:
        assert "name" in crit
        assert "score" in crit
        assert "max" in crit
        assert "percent" in crit
        assert "level" in crit
        assert "type" in crit

        if crit["percent"] >= 80:
            assert crit["level"] == "Bueno"
            assert crit["type"] == "success"
        elif crit["percent"] >= 60:
            assert crit["level"] == "En progreso"
            assert crit["type"] == "warning"
        else:
            assert crit["level"] == "Bajo"
            assert crit["type"] == "alert"

        assert crit["score"] <= crit["max"]

    # Check evidence structure (up to 10 events)
    assert len(data["evidence"]) <= 10
    assert len(data["evidence"]) > 0
    first_ev = data["evidence"][0]
    assert "id" in first_ev
    assert first_ev["type"] in ("commit", "pr")
    assert "text" in first_ev
    assert "author" in first_ev
    assert "when" in first_ev
    assert first_ev["when"] > 1e11


def test_analysis_group_without_events(client: TestClient, mock_db):
    """GET /groups/{id}/analysis returns 0 metrics and empty evidence when group has no events."""
    seed_database(mock_db)
    mock_db[FEEDBACK_COLLECTION].insert_one(
        {"groupId": 99, "courseId": 1, "groupName": "Grupo 99"}
    )

    # Group 99 has no events in seed data
    response = client.get("/groups/99/analysis")
    assert response.status_code == 200
    data = response.json()

    assert data["score"] == 0.0
    assert data["progress"] == 0
    assert len(data["evidence"]) == 0
    for crit in data["criteria"]:
        assert crit["percent"] == 0
        assert crit["score"] == 0.0
        assert crit["level"] == "Bajo"
        assert crit["type"] == "alert"


def test_progress_summary(client: TestClient, mock_db):
    """GET /groups/{id}/progress-summary returns status by criterion."""
    seed_database(mock_db)

    # 404 when no course rubric
    mock_db[COURSE_SETTINGS_COLLECTION].delete_many({})
    assert client.get("/groups/1/progress-summary").status_code == 404

    # Restore seed and verify 200
    seed_database(mock_db)
    res = client.get("/groups/1/progress-summary")
    assert res.status_code == 200
    data = res.json()
    assert data["groupId"] == 1
    assert "overall" in data
    assert "items" in data
    assert len(data["items"]) == 3
    for item in data["items"]:
        assert "criterionId" in item
        assert item["status"] in ("on_track", "at_risk", "delayed")
        assert "note" in item


def test_group_criteria(client: TestClient, mock_db):
    """GET /groups/{id}/criteria returns compliance per criterion."""
    seed_database(mock_db)

    # 404 when no course rubric
    mock_db[COURSE_SETTINGS_COLLECTION].delete_many({})
    assert client.get("/groups/1/criteria").status_code == 404

    seed_database(mock_db)
    res = client.get("/groups/1/criteria")
    assert res.status_code == 200
    data = res.json()
    assert data["groupId"] == 1
    assert "items" in data
    assert len(data["items"]) == 3
    for item in data["items"]:
        assert "criterionId" in item
        assert "name" in item
        assert item["level"] in ("met", "partial", "not_met")
        assert "score" in item


def test_issues_detection_and_queue_event(client: TestClient, mock_db, fake_queue):
    """GET /groups/{id}/issues detects commit issues, stores them, and publishes events."""
    seed_database(mock_db)

    # Call /issues on group 1 (which has wip and test commits)
    res = client.get("/groups/1/issues?page=1&pageSize=10")
    assert res.status_code == 200
    data = res.json()

    assert "totalRecords" in data
    assert "page" in data
    assert "pageSize" in data
    assert "items" in data
    assert data["totalRecords"] >= 2  # g1_c03 (wip) and g1_c06 (test)
    assert len(data["items"]) >= 2

    # Verify queue message was published
    assert len(fake_queue.published_events) >= 2
    ev = fake_queue.published_events[0]
    assert "eventId" in ev
    assert ev["type"] == "ISSUE_DETECTED"
    assert isinstance(ev["courseId"], int)
    assert isinstance(ev["groupId"], int)
    assert len(ev["title"]) > 0
    assert len(ev["message"]) > 0
    assert isinstance(ev["createdAt"], int)
    assert ev["createdAt"] > 1e11  # Miliseconds, not seconds
    assert ev["source"] == "ms-analysis"

    # Idempotence: calling /issues again should NOT duplicate issues in DB or emit duplicate events
    initial_event_count = len(fake_queue.published_events)
    res2 = client.get("/groups/1/issues?page=1&pageSize=10")
    assert res2.status_code == 200
    assert res2.json()["totalRecords"] == data["totalRecords"]
    assert len(fake_queue.published_events) == initial_event_count


def test_issues_400_invalid_pagination(client: TestClient, mock_db):
    """GET /groups/{id}/issues returns 400 when page or pageSize are invalid."""
    seed_database(mock_db)

    # page < 1
    res1 = client.get("/groups/1/issues?page=0&pageSize=10")
    assert res1.status_code == 400
    assert "error" in res1.json()

    # pageSize < 1
    res2 = client.get("/groups/1/issues?page=1&pageSize=0")
    assert res2.status_code == 400
    assert "error" in res2.json()

    # pageSize > 100
    res3 = client.get("/groups/1/issues?page=1&pageSize=101")
    assert res3.status_code == 400
    assert "error" in res3.json()


def test_issues_404_no_rubric(client: TestClient, mock_db):
    """GET /groups/{id}/issues returns 404 when course has no rubric."""
    mock_db[FEEDBACK_COLLECTION].insert_one(
        {"groupId": 888, "courseId": 888, "groupName": "Grupo 888"}
    )
    res = client.get("/groups/888/issues")
    assert res.status_code == 404
    assert res.json()["error"] == "El curso 888 no tiene una rúbrica configurada" 


def test_issues_use_group_name_from_feedback(client: TestClient, mock_db):
    """Los inconvenientes muestran el nombre del grupo guardado en feedback, no 'Grupo {id}'."""
    seed_database(mock_db)
    mock_db[FEEDBACK_COLLECTION].update_one(
        {"groupId": 1},
        {"$set": {"groupName": "Grupo 1 - Sistema de Inventario"}},
    )
    res = client.get("/groups/1/issues")
    assert res.status_code == 200
    assert all(i["groupName"] == "Grupo 1 - Sistema de Inventario" for i in res.json()["items"])
    # Sin groupName en documento de feedback se conserva el valor por defecto ('Grupo {id}')
    mock_db[FEEDBACK_COLLECTION].update_one({"groupId": 1}, {"$unset": {"groupName": ""}})
    res2 = client.get("/groups/1/issues")
    assert res2.status_code == 200
    assert all(i["groupName"] == "Grupo 1" for i in res2.json()["items"])


def test_unconfigured_group_404_all_endpoints(client: TestClient):
    """Un grupo sin documento devuelve 404 con {'error': 'El grupo 999 no está configurado en MS2'} en todos los endpoints de grupo."""
    endpoints = [
        "/groups/999/analysis",
        "/groups/999/criteria",
        "/groups/999/progress-summary",
        "/groups/999/issues",
        "/groups/999/feedback",
        "/groups/999/report",
    ]
    expected_error = "El grupo 999 no está configurado en MS2"
    for ep in endpoints:
        res = client.get(ep)
        assert res.status_code == 404, f"Fallo en {ep}: status {res.status_code}"
        assert res.json() == {"error": expected_error}, f"Fallo en {ep}: {res.json()}" 