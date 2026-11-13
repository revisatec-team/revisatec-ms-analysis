import time
"""Tests for feedback, publish queue integration, and direct reviews."""
from fastapi.testclient import TestClient
from app.db.cosmos import (
    COURSE_SETTINGS_COLLECTION,
    FEEDBACK_COLLECTION,
    DIRECT_REVIEWS_COLLECTION,
    GITHUB_EVENTS_COLLECTION,
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
    """PUT /groups/{id}/feedback creates or updates professor review with AI draft."""
    seed_database(mock_db)

    # 404 if group is not configured in MS2
    res_404 = client.put("/groups/999/feedback", json={"professor": "Excelente trabajo."})
    assert res_404.status_code == 404
    assert res_404.json() == {"error": "El grupo 999 no está configurado en MS2"}

    # 400 if professor field is missing
    res_400 = client.put("/groups/1/feedback", json={})
    assert res_400.status_code == 400

    # Successful update without prior GET: creates doc with AI draft and professor review
    res = client.put("/groups/1/feedback", json={"professor": "Excelente trabajo."})
    assert res.status_code == 200
    assert res.json()["professor"] == "Excelente trabajo."
    assert "El grupo obtiene" in res.json()["ai"]
    assert res.json()["status"] == "draft"

    # Subsequent update updates professor text
    res2 = client.put("/groups/1/feedback", json={"professor": "Buen trabajo en los PRs."})
    assert res2.status_code == 200
    assert res2.json()["professor"] == "Buen trabajo en los PRs."


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


def test_publish_feedback_queue_event_uses_real_group_name(client: TestClient, mock_db, fake_queue):
    """El mensaje del evento FEEDBACK_PUBLISHED en la cola contiene el groupName real del grupo."""
    seed_database(mock_db)
    mock_db[FEEDBACK_COLLECTION].update_one(
        {"groupId": 1},
        {"$set": {"groupName": "Grupo 1 - Plataforma de Reservas"}},
    )
    client.get("/groups/1/feedback")
    client.put("/groups/1/feedback", json={"professor": "Buen trabajo en los PRs."})

    fake_queue.clear()
    res = client.post("/groups/1/feedback/publish")
    assert res.status_code == 200
    assert len(fake_queue.published_events) == 1
    ev = fake_queue.published_events[0]
    assert ev["type"] == "FEEDBACK_PUBLISHED"
    assert "Se publicó la retroalimentación de Grupo 1 - Plataforma de Reservas" in ev["message"]


def test_publish_feedback_twice_returns_409(client: TestClient, mock_db, fake_queue):
    """Publicar dos veces devuelve 409 en la segunda llamada y la cola solo tiene un evento."""
    seed_database(mock_db)
    client.get("/groups/1/feedback")
    client.put("/groups/1/feedback", json={"professor": "Revisión final aprobada."})

    fake_queue.clear()
    # Primera publicación: 200 OK
    res1 = client.post("/groups/1/feedback/publish")
    assert res1.status_code == 200
    assert len(fake_queue.published_events) == 1

    # Segunda publicación: 409 Conflict
    res2 = client.post("/groups/1/feedback/publish")
    assert res2.status_code == 409
    assert res2.json() == {"error": "La retroalimentación ya fue publicada"}
    # La cola solo tiene el primer evento
    assert len(fake_queue.published_events) == 1


def test_feedback_recalculation_for_draft_and_frozen_for_published(client: TestClient, mock_db):
    """GET recalcula score y ai si el status es draft; no recalcula si es published."""
    seed_database(mock_db)

    # 1. Crear borrador inicial con GET
    res1 = client.get("/groups/1/feedback")
    assert res1.status_code == 200
    initial_score = res1.json()["score"]

    # Agregar commits para cambiar la métrica y nota
    now_ms = int(time.time() * 1000)
    new_commits = [
        {
            "id": f"g1_recalc_{i}",
            "groupId": 1,
            "type": "commit",
            "author": "estudiante1",
            "reviewers": [],
            "message": f"feat: commit de avance adicional {i}",
            "createdAt": now_ms - (i * 1000),
        }
        for i in range(25)
    ]
    mock_db[GITHUB_EVENTS_COLLECTION].insert_many(new_commits)

    # Como status es 'draft', GET debe recalcular
    res2 = client.get("/groups/1/feedback")
    assert res2.status_code == 200
    assert res2.json()["score"] != initial_score

    # Ahora publicamos el feedback
    client.put("/groups/1/feedback", json={"professor": "Listo para publicar."})
    res_pub = client.post("/groups/1/feedback/publish")
    assert res_pub.status_code == 200
    published_ai = res_pub.json()["ai"]
    published_score = res_pub.json()["score"]

    # Borramos todos los eventos para que un recálculo daría 0
    mock_db[GITHUB_EVENTS_COLLECTION].delete_many({"groupId": 1})

    # Como status es 'published', GET NO debe recalcular nada (queda congelado)
    res_frozen = client.get("/groups/1/feedback")
    assert res_frozen.status_code == 200
    assert res_frozen.json()["score"] == published_score
    assert res_frozen.json()["ai"] == published_ai
    assert res_frozen.json()["status"] == "published"


def test_feedback_notified_persisted_on_queue_failure(client: TestClient, mock_db, fake_queue):
    """Con cola fallida (fake_queue.should_fail = True), un GET posterior devuelve notified false; con éxito devuelve true."""
    seed_database(mock_db)
    client.get("/groups/1/feedback")
    client.put("/groups/1/feedback", json={"professor": "Revisión lista."})

    fake_queue.should_fail = True
    res_pub = client.post("/groups/1/feedback/publish")
    assert res_pub.status_code == 200
    assert res_pub.json()["notified"] is False

    # GET posterior devuelve notified=false persistido
    res_get = client.get("/groups/1/feedback")
    assert res_get.status_code == 200
    assert res_get.json()["notified"] is False

    # Probar con grupo 2 en caso exitoso
    client.get("/groups/2/feedback")
    client.put("/groups/2/feedback", json={"professor": "Aprobado grupo 2."})
    fake_queue.should_fail = False
    res_pub2 = client.post("/groups/2/feedback/publish")
    assert res_pub2.status_code == 200
    assert res_pub2.json()["notified"] is True

    res_get2 = client.get("/groups/2/feedback")
    assert res_get2.status_code == 200
    assert res_get2.json()["notified"] is True


def test_generate_ai_feedback_single_criterion_and_ties(client: TestClient, mock_db):
    """_generate_ai_feedback omite 'A mejorar' y usa 'Rendimiento parejo' cuando hay 1 criterio o empates."""
    # 1. Caso un solo criterio
    mock_db[COURSE_SETTINGS_COLLECTION].insert_one({
        "courseId": 70,
        "rubric": {
            "criteria": [{"name": "Criterio Unico", "weight": 100.0}],
            "version": 1,
            "interpretationStatus": "manual",
        },
    })
    mock_db[FEEDBACK_COLLECTION].insert_one({
        "groupId": 701,
        "courseId": 70,
        "groupName": "Grupo 701",
    })

    res_single = client.get("/groups/701/feedback")
    assert res_single.status_code == 200
    ai_single = res_single.json()["ai"]
    assert "Rendimiento parejo en todos los criterios (" in ai_single
    assert "A mejorar" not in ai_single
    assert "Fortaleza" not in ai_single

    # 2. Caso empates en todos los criterios (múltiples criterios con mismo %)
    mock_db[COURSE_SETTINGS_COLLECTION].insert_one({
        "courseId": 80,
        "rubric": {
            "criteria": [
                {"name": "Calidad de codigo", "weight": 50.0},
                {"name": "Revisiones de pares", "weight": 50.0},
            ],
            "version": 1,
            "interpretationStatus": "manual",
        },
    })
    mock_db[FEEDBACK_COLLECTION].insert_one({
        "groupId": 801,
        "courseId": 80,
        "groupName": "Grupo 801",
    })

    # Sin eventos, ambos criterios tienen 0%
    res_ties = client.get("/groups/801/feedback")
    assert res_ties.status_code == 200
    ai_ties = res_ties.json()["ai"]
    assert "Rendimiento parejo en todos los criterios (0%)" in ai_ties
    assert "A mejorar" not in ai_ties
    assert "Fortaleza" not in ai_ties


def test_update_feedback_published_returns_409(client: TestClient, mock_db):
    """PUT /groups/{id}/feedback en retroalimentación ya publicada responde 409 y no se puede editar."""
    seed_database(mock_db)
    client.get("/groups/1/feedback")
    client.put("/groups/1/feedback", json={"professor": "Original antes de publicar."})
    res_pub = client.post("/groups/1/feedback/publish")
    assert res_pub.status_code == 200

    # Intentar editar con PUT responde 409
    res_edit = client.put("/groups/1/feedback", json={"professor": "Intento de edición posterior."})
    assert res_edit.status_code == 409
    assert res_edit.json() == {"error": "La retroalimentación ya fue publicada y no se puede editar"}

    # Confirmar que el texto del profesor no fue alterado
    res_get = client.get("/groups/1/feedback")
    assert res_get.status_code == 200
    assert res_get.json()["professor"] == "Original antes de publicar."
