"""Pytest configuration and common fixtures."""
import pytest
import mongomock
from fastapi.testclient import TestClient

from app.main import app
from app.db.cosmos import set_database
from app.services.queue_publisher import FakeQueuePublisher, set_publisher


@pytest.fixture(autouse=True)
def mock_db():
    """Inject an in-memory mongomock database for all tests."""
    client = mongomock.MongoClient()
    db = client["revisatec"]
    set_database(db)
    yield db
    set_database(None)


@pytest.fixture(autouse=True)
def fake_queue():
    """Inject a FakeQueuePublisher for all tests."""
    publisher = FakeQueuePublisher()
    set_publisher(publisher)
    yield publisher
    set_publisher(None)


@pytest.fixture
def client():
    """Provide a TestClient for FastAPI."""
    with TestClient(app) as test_client:
        yield test_client
