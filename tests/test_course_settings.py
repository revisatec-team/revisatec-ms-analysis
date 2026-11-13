"""Tests for course settings endpoints: rubric, instructions, scraping-config."""
import time
from fastapi.testclient import TestClient
from app.db.cosmos import (
    COURSE_SETTINGS_COLLECTION,
    GITHUB_EVENTS_COLLECTION,
    FEEDBACK_COLLECTION,
)
from scripts.seed import seed_database


# --- Rubric tests ---

def test_get_rubric_404(client: TestClient):
    """GET /courses/{id}/rubric returns 404 when course has no rubric."""
    response = client.get("/courses/999/rubric")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert "no encontrada" in data["error"].lower()


def test_put_rubric_success_and_get(client: TestClient):
    """PUT /courses/{id}/rubric creates or updates rubric, then GET retrieves it."""
    payload = {
        "fileName": "rubrica_inicial.pdf",
        "interpretationStatus": "Interpretada por IA",
        "criteria": [
            {"name": "Calidad de código", "weight": 60.0},
            {"name": "Pruebas", "weight": 40.0},
        ],
    }
    put_res = client.put("/courses/10/rubric", json=payload)
    assert put_res.status_code == 200
    put_data = put_res.json()
    assert put_data["fileName"] == "rubrica_inicial.pdf"
    assert put_data["interpretationStatus"] == "Interpretada por IA"
    assert len(put_data["criteria"]) == 2

    # Verify GET
    get_res = client.get("/courses/10/rubric")
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data == put_data


def test_put_rubric_preserves_metadata_when_omitted(client: TestClient):
    """PUT /courses/{id}/rubric preserves fileName and interpretationStatus if not provided."""
    initial_payload = {
        "fileName": "original.pdf",
        "interpretationStatus": "Interpretada por IA",
        "criteria": [
            {"name": "Criterio A", "weight": 50.0},
            {"name": "Criterio B", "weight": 50.0},
        ],
    }
    client.put("/courses/11/rubric", json=initial_payload)

    # Update only criteria, omit fileName and interpretationStatus
    update_payload = {
        "criteria": [
            {"name": "Criterio A modificado", "weight": 70.0},
            {"name": "Criterio B modificado", "weight": 30.0},
        ]
    }
    res = client.put("/courses/11/rubric", json=update_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["fileName"] == "original.pdf"
    assert data["interpretationStatus"] == "Interpretada por IA"
    assert len(data["criteria"]) == 2
    assert data["criteria"][0]["name"] == "Criterio A modificado"


def test_put_rubric_400_weights_sum(client: TestClient):
    """PUT /courses/{id}/rubric returns 400 when weights do not sum to 100."""
    payload = {
        "criteria": [
            {"name": "Criterio A", "weight": 40.0},
            {"name": "Criterio B", "weight": 40.0},
        ]
    }
    res = client.put("/courses/10/rubric", json=payload)
    assert res.status_code == 400
    assert "error" in res.json()


def test_put_rubric_400_empty_criteria(client: TestClient):
    """PUT /courses/{id}/rubric returns 400 when criteria list is empty."""
    payload = {"criteria": []}
    res = client.put("/courses/10/rubric", json=payload)
    assert res.status_code == 400
    assert "error" in res.json()


def test_put_rubric_400_weight_out_of_range(client: TestClient):
    """PUT /courses/{id}/rubric returns 400 when a criterion weight is negative or > 100."""
    payload = {
        "criteria": [
            {"name": "Criterio A", "weight": 150.0},
            {"name": "Criterio B", "weight": -50.0},
        ]
    }
    res = client.put("/courses/10/rubric", json=payload)
    assert res.status_code == 400
    assert "error" in res.json()


# --- Instructions tests ---

def test_get_instructions_404(client: TestClient):
    """GET /courses/{id}/instructions returns 404 when missing."""
    response = client.get("/courses/999/instructions")
    assert response.status_code == 404
    assert "error" in response.json()


def test_put_instructions_success_and_get(client: TestClient):
    """PUT /courses/{id}/instructions updates text and GET retrieves it."""
    payload = {"text": "Revisar especialmente los pull requests de arquitectura."}
    put_res = client.put("/courses/20/instructions", json=payload)
    assert put_res.status_code == 200
    assert put_res.json() == payload

    get_res = client.get("/courses/20/instructions")
    assert get_res.status_code == 200
    assert get_res.json()["text"] == payload["text"]


def test_put_instructions_400_max_length(client: TestClient):
    """PUT /courses/{id}/instructions returns 400 when text exceeds 1000 chars."""
    payload = {"text": "a" * 1001}
    res = client.put("/courses/20/instructions", json=payload)
    assert res.status_code == 400
    assert "error" in res.json()


# --- ScrapingConfig tests ---

def test_get_scraping_config_404(client: TestClient):
    """GET /courses/{id}/scraping-config returns 404 when missing."""
    response = client.get("/courses/999/scraping-config")
    assert response.status_code == 404
    assert "error" in response.json()


def test_put_scraping_config_success_and_next_run(client: TestClient):
    """PUT /courses/{id}/scraping-config updates config and recalculates nextRunAt."""
    now_ms = int(time.time() * 1000)
    payload = {
        "frequency": "daily",
        "minReviewers": 2,
    }
    put_res = client.put("/courses/30/scraping-config", json=payload)
    assert put_res.status_code == 200
    data = put_res.json()
    assert data["frequency"] == "daily"
    assert data["minReviewers"] == 2
    assert "nextRunAt" in data
    # daily adds approximately 86,400,000 ms
    diff = data["nextRunAt"] - now_ms
    assert 86_000_000 < diff < 87_000_000

    # Test hourly recalculation
    hourly_payload = {
        "frequency": "hourly",
        "minReviewers": 1,
    }
    hourly_res = client.put("/courses/30/scraping-config", json=hourly_payload)
    assert hourly_res.status_code == 200
    h_data = hourly_res.json()
    assert h_data["frequency"] == "hourly"
    h_diff = h_data["nextRunAt"] - now_ms
    assert 3_500_000 < h_diff < 3_700_000

    # Verify GET
    get_res = client.get("/courses/30/scraping-config")
    assert get_res.status_code == 200
    assert get_res.json()["nextRunAt"] == h_data["nextRunAt"]


def test_put_scraping_config_400_invalid_frequency(client: TestClient):
    """PUT /courses/{id}/scraping-config returns 400 with invalid frequency."""
    payload = {
        "frequency": "monthly",
        "minReviewers": 1,
    }
    res = client.put("/courses/30/scraping-config", json=payload)
    assert res.status_code == 400
    assert "error" in res.json()


def test_put_scraping_config_400_min_reviewers(client: TestClient):
    """PUT /courses/{id}/scraping-config returns 400 when minReviewers < 1."""
    payload = {
        "frequency": "daily",
        "minReviewers": 0,
    }
    res = client.put("/courses/30/scraping-config", json=payload)
    assert res.status_code == 400
    assert "error" in res.json()


# --- Seed Idempotence test ---

def test_seed_idempotency(mock_db):
    """Test that seed_database is idempotent and does not duplicate documents."""
    result1 = seed_database(mock_db)
    assert result1["course_settings_count"] == 1
    assert result1["github_events_count"] == result1["total_events"]
    assert result1["feedback_count"] == result1["total_feedback"]

    # Re-run seed on the same database
    result2 = seed_database(mock_db)
    assert result2["course_settings_count"] == 1
    assert result2["github_events_count"] == result1["total_events"]
    assert result2["feedback_count"] == result1["total_feedback"]

    # Verify exact collection counts directly in DB
    assert mock_db[COURSE_SETTINGS_COLLECTION].count_documents({}) == 1
    assert mock_db[GITHUB_EVENTS_COLLECTION].count_documents({}) == result1["total_events"]
    assert mock_db[FEEDBACK_COLLECTION].count_documents({}) == result1["total_feedback"]


def test_upsert_course_settings_duplicate_key_error_retry(mock_db, monkeypatch):
    """Verifica que _upsert_course_settings captura DuplicateKeyError en update_one con upsert=True y reintenta sin upsert."""
    from app.services.course_settings import _upsert_course_settings
    from pymongo.errors import DuplicateKeyError

    # Pre-crear el documento en la base de datos para que el segundo intento (upsert=False) tenga qué actualizar
    mock_db[COURSE_SETTINGS_COLLECTION].insert_one({"courseId": 500, "instructions": {"text": "Original"}})

    real_update_one = mock_db[COURSE_SETTINGS_COLLECTION].update_one
    first_call = True

    def mock_update_one(filter, update, upsert=False, **kwargs):
        nonlocal first_call
        if first_call and upsert:
            first_call = False
            raise DuplicateKeyError("E11000 duplicate key error")
        return real_update_one(filter, update, upsert=upsert, **kwargs)

    monkeypatch.setattr(mock_db[COURSE_SETTINGS_COLLECTION], "update_one", mock_update_one)

    # Llamar _upsert_course_settings
    _upsert_course_settings(500, {"rubric": {"criteria": []}})

    doc = mock_db[COURSE_SETTINGS_COLLECTION].find_one({"courseId": 500})
    assert doc is not None
    assert "rubric" in doc
    assert doc["instructions"]["text"] == "Original"
    assert not first_call  # Se disparó la excepción y se reintentó
