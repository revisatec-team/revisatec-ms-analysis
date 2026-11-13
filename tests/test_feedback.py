"""Tests for feedback, publish queue integration, and direct reviews."""
from fastapi.testclient import TestClient
from app.db.cosmos import (
    COURSE_SETTINGS_COLLECTION,
    FEEDBACK_COLLECTION,
    DIRECT_REVIEWS_COLLECTION,
)
from scripts.seed import seed_database


def test_feedback_404_no_rubric(client: TestClient, mock_db):
    """GET /groups/{id}/feedback returns 404 if course has no rubric."""
    mock_db[FEEDBACK_COLLECTION].insert_one(
        {"groupId": 888, "courseId": 888, "groupName": "Grupo 888"}
    )
    res = client.get("/groups/888/feedback")
    assert res.status_code == 404
    assert res.json()["error"] == "El curso 888 no tiene una rúbrica configurada"


def test_feedback_404_unconfigured_group(client: TestClient):
    """GET /groups/{id}/feedback returns 404 when group is not configured in MS2."""
    res = client.get("/groups/999/feedback")
    assert res.status_code == 404
    assert res.json() == {"error": "El grupo 999 no está configurado en MS2"}


def test_get_feedback_creates_draft(client: TestClient, mock_db):
    """GET /groups/{id}/feedback creates initial AI draft if not yet existing."""
    seed_database(mock_db)

    # First call generates draft
    res = client.get("/groups/1/feedback")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "draft"
    assert "El grupo obtiene" in data["ai"]
    assert "Fortaleza:" in data["ai"]
    assert "A mejorar:" in data["ai"]
    assert data["professor"] == ""

    # Second call returns existing draft
    res2 = client.get("/groups/1/feedback")
    assert res2.status_code == 200
    assert res2.json()["ai"] == data["ai"]


def test_update_feedback(client: TestClient, mock_db):
    """PUT /groups/{id}/feedback updates professor review."""
    seed_database(mock_db)

    # 404 if feedback does not exist
    res_404 = client.put("/groups/1/feedback", json={"professor": "Excelente trabajo."})
    assert res_404.status_code == 404

    # Create draft first
    client.get("/groups/1/feedback")

    # 400 if professor field is missing
    res_400 = client.put("/groups/1/feedback", json={})
    assert res_400.status_code == 400

    # Successful update
    res = client.put("/groups/1/feedback", json={"professor": "Buen trabajo en los PRs."})
    assert res.status_code == 200
    assert res.json()["professor"] == "Buen trabajo en los PRs."


def test_publish_feedback_success_and_queue(client: TestClient, mock_db, fake_queue):
    """POST /groups/{id}/feedback/publish validates professor text, marks published, and emits queue event."""
    seed_database(mock_db)
    client.get("/groups/1/feedback")

    # 400 because professor text is still empty
    res_fail = client.post("/groups/1/feedback/publish")
    assert res_fail.status_code == 400
    assert "falta" in res_fail.json()["error"].lower()

    # Fill professor review
    client.put("/groups/1/feedback", json={"professor": "Aprobado con observaciones."})

    # Publish
    fake_queue.clear()
    res = client.post("/groups/1/feedback/publish")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "published"
    assert data["publishedAt"] is not None
    assert data["publishedAt"] > 1e11
    assert data["notified"] is True

    # Verify queue message
    assert len(fake_queue.published_events) == 1
    ev = fake_queue.published_events[0]
    assert ev["type"] == "FEEDBACK_PUBLISHED"
    assert ev["groupId"] == 1
    assert isinstance(ev["courseId"], int)
    assert ev["title"] == "Retroalimentación publicada"
    assert "Se publicó la retroalimentación de Grupo 1" in ev["message"]
    assert ev["createdAt"] > 1e11
    assert ev["source"] == "ms-analysis"


def test_publish_feedback_queue_failure_preserves_published(client: TestClient, mock_db, fake_queue):
    """When queue fails, publication is preserved and response indicates notified: false."""
    seed_database(mock_db)
    client.get("/groups/2/feedback")
    client.put("/groups/2/feedback", json={"professor": "Revisado."})

    # Simulate queue failure
    fake_queue.should_fail = True
    res = client.post("/groups/2/feedback/publish")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "published"
    assert data["notified"] is False

    # Check that in DB it is still published
    doc = mock_db[FEEDBACK_COLLECTION].find_one({"groupId": 2})
    assert doc["status"] == "published"


def test_direct_reviews_lifecycle(client: TestClient, mock_db):
    """Test POST and GET /groups/{id}/direct-reviews."""
    seed_database(mock_db)

    # 404 when group's course has no rubric
    mock_db[FEEDBACK_COLLECTION].insert_one({"groupId": 999, "courseId": 999})
    assert client.post("/groups/999/direct-reviews", json={"note": "Test"}).status_code == 404
    assert client.get("/groups/999/direct-reviews").status_code == 404

    # 400 on empty note
    res_400 = client.post("/groups/1/direct-reviews", json={"note": "   "})
    assert res_400.status_code == 400
    assert "error" in res_400.json()

    # 201 Created
    res_post = client.post("/groups/1/direct-reviews", json={"note": "Revisión presencial de arquitectura."})
    assert res_post.status_code == 201
    rev = res_post.json()
    assert "id" in rev
    assert rev["note"] == "Revisión presencial de arquitectura."
    assert rev["date"] > 1e11

    # GET list
    res_get = client.get("/groups/1/direct-reviews?page=1&pageSize=10")
    assert res_get.status_code == 200
    list_data = res_get.json()
    assert list_data["totalRecords"] == 1
    assert len(list_data["items"]) == 1
    assert list_data["items"][0]["id"] == rev["id"]

    # 400 on invalid pagination
    assert client.get("/groups/1/direct-reviews?page=0").status_code == 400
    assert client.get("/groups/1/direct-reviews?pageSize=150").status_code == 400


def test_queue_message_contract_compliance(client: TestClient, mock_db, fake_queue):
    """Verify queue message contract: eventId unique, createdAt > 1e11 (ms), ids int, type valid."""
    seed_database(mock_db)

    # Trigger issue detection
    fake_queue.clear()
    client.get("/groups/1/issues")

    # Trigger feedback publish
    client.get("/groups/1/feedback")
    client.put("/groups/1/feedback", json={"professor": "Listo."})
    client.post("/groups/1/feedback/publish")

    assert len(fake_queue.published_events) >= 2
    event_ids = set()

    for event in fake_queue.published_events:
        assert isinstance(event["eventId"], str)
        assert len(event["eventId"]) > 0
        assert event["eventId"] not in event_ids
        event_ids.add(event["eventId"])

        assert event["type"] in ("FEEDBACK_PUBLISHED", "ISSUE_DETECTED")
        assert isinstance(event["courseId"], int)
        assert isinstance(event["groupId"], int)
        assert isinstance(event["title"], str) and len(event["title"]) > 0
        assert isinstance(event["message"], str) and len(event["message"]) > 0
        assert isinstance(event["createdAt"], int)
        assert event["createdAt"] > 1e11  # Epoch ms strictly > 1e11
        assert event["source"] == "ms-analysis"
