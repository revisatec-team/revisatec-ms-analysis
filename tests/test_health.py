"""Tests for /health, Cosmos connection, and global error handlers."""
import time
from fastapi.testclient import TestClient
from app.db.cosmos import get_database, COURSE_SETTINGS_COLLECTION


def test_health_success(client: TestClient):
    """Test GET /health returns expected schema and fields."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "revisatec-ms-analysis"
    assert isinstance(data["timestamp"], int)
    # Check that timestamp is in epoch milliseconds (recent timestamp > 1e11)
    assert data["timestamp"] > 1e11
    assert abs(data["timestamp"] - int(time.time() * 1000)) < 10000


def test_not_found_global_handler(client: TestClient):
    """Test that a non-existent route returns 404 with error key."""
    response = client.get("/non-existent-endpoint")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert isinstance(data["error"], str)
    assert len(data["error"]) > 0


def test_validation_error_handler(client: TestClient):
    """Test that validation error returns 400 with {'error': 'mensaje'}."""
    from app.main import app
    from pydantic import BaseModel, Field

    class SampleInput(BaseModel):
        count: int = Field(..., ge=1)

    @app.post("/test-validation")
    def sample_endpoint(payload: SampleInput):
        return {"received": payload.count}

    # Pass negative count to trigger validation error
    response = client.post("/test-validation", json={"count": -5})
    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert isinstance(data["error"], str)
    assert len(data["error"]) > 0


def test_cosmos_db_injection(mock_db):
    """Test that Cosmos DB mock client works and can read/write."""
    db = get_database()
    assert db is not None
    db[COURSE_SETTINGS_COLLECTION].insert_one({"courseId": 1, "test": True})
    doc = db[COURSE_SETTINGS_COLLECTION].find_one({"courseId": 1})
    assert doc is not None
    assert doc["test"] is True


def test_internal_server_error_handler():
    """Test that unhandled exceptions return 500 with {'error': 'Error interno del servidor'}."""
    from app.main import app

    @app.get("/test-unhandled-exception")
    def sample_failing_endpoint():
        raise RuntimeError("Fallo inesperado del sistema")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/test-unhandled-exception")
    assert response.status_code == 500
    assert response.json() == {"error": "Error interno del servidor"}
