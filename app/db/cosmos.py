"""Cosmos DB (MongoDB API) connectivity and collection helpers."""
import logging
from typing import Optional
from pymongo import MongoClient
from pymongo.database import Database
from app.config import settings

logger = logging.getLogger(__name__)

_mongo_client: Optional[MongoClient] = None
_database_override: Optional[Database] = None

# Collection names as defined in specification
RUBRICS_COLLECTION = "rubrics"
INSTRUCTIONS_COLLECTION = "instructions"
SCRAPING_CONFIGS_COLLECTION = "scraping_configs"
ANALYSES_COLLECTION = "analyses"
FEEDBACKS_COLLECTION = "feedbacks"
ISSUES_COLLECTION = "issues"
DIRECT_REVIEWS_COLLECTION = "direct_reviews"
REPORTS_COLLECTION = "reports"
MEMBERS_COLLECTION = "members"


def get_client() -> MongoClient:
    """Return the active MongoClient instance, creating one if not yet initialized."""
    global _mongo_client
    if _mongo_client is None:
        conn_str = settings.COSMOS_CONNECTION_STRING
        if not conn_str:
            # Fallback for local development or in-memory tests if no connection string is provided
            logger.warning("COSMOS_CONNECTION_STRING is not set. Using localhost default.")
            _mongo_client = MongoClient("mongodb://localhost:27017")
        else:
            _mongo_client = MongoClient(conn_str)
    return _mongo_client


def get_database() -> Database:
    """Return the active MongoDB/Cosmos database instance."""
    global _database_override
    if _database_override is not None:
        return _database_override
    client = get_client()
    return client[settings.COSMOS_DB_NAME]


def set_database(db: Optional[Database]) -> None:
    """Override the database instance (e.g. for testing with mongomock)."""
    global _database_override
    _database_override = db


def close_client() -> None:
    """Close the active MongoClient."""
    global _mongo_client
    if _mongo_client is not None:
        try:
            _mongo_client.close()
        except Exception:
            pass
        _mongo_client = None
