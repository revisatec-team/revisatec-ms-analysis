"""Cosmos DB (MongoDB API) connectivity and collection helpers."""
import logging
from typing import Optional
from pymongo import MongoClient
from pymongo.database import Database
from app.config import settings

logger = logging.getLogger(__name__)

_mongo_client: Optional[MongoClient] = None
_database_override: Optional[Database] = None

# Exact collection names according to docs/cosmos-model.md
COURSE_SETTINGS_COLLECTION = "course_settings"
GITHUB_EVENTS_COLLECTION = "github_events"
FEEDBACK_COLLECTION = "feedback"
ISSUES_COLLECTION = "issues"
DIRECT_REVIEWS_COLLECTION = "direct_reviews"
REPORT_CHECKLIST_COLLECTION = "report_checklist"


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
    if db is not None:
        init_indexes(db)


def init_indexes(db: Optional[Database] = None) -> None:
    """Create indexes according to docs/cosmos-model.md idempotently."""
    if db is None:
        try:
            db = get_database()
        except Exception as e:
            logger.warning(f"Could not get database to initialize indexes: {e}")
            return

    try:
        # course_settings: courseId (único)
        db[COURSE_SETTINGS_COLLECTION].create_index("courseId", unique=True)
    except Exception as e:
        logger.warning(f"Index course_settings.courseId already exists or skipped: {e}")

    try:
        # github_events: groupId, createdAt (simple and compound)
        db[GITHUB_EVENTS_COLLECTION].create_index("groupId")
    except Exception as e:
        logger.warning(f"Index github_events.groupId already exists or skipped: {e}")

    try:
        db[GITHUB_EVENTS_COLLECTION].create_index("createdAt")
    except Exception as e:
        logger.warning(f"Index github_events.createdAt already exists or skipped: {e}")

    try:
        db[GITHUB_EVENTS_COLLECTION].create_index([("groupId", 1), ("createdAt", 1)])
    except Exception as e:
        logger.warning(f"Index github_events compound already exists or skipped: {e}")

    try:
        # feedback: groupId (único)
        db[FEEDBACK_COLLECTION].create_index("groupId", unique=True)
    except Exception as e:
        logger.warning(f"Index feedback.groupId already exists or skipped: {e}")

    try:
        # issues: groupId, date, sourceEventId (simple and compound)
        db[ISSUES_COLLECTION].create_index("groupId")
    except Exception as e:
        logger.warning(f"Index issues.groupId already exists or skipped: {e}")

    try:
        db[ISSUES_COLLECTION].create_index("date")
    except Exception as e:
        logger.warning(f"Index issues.date already exists or skipped: {e}")

    try:
        db[ISSUES_COLLECTION].create_index("sourceEventId", unique=True)
    except Exception as e:
        logger.warning(f"Index issues.sourceEventId already exists or skipped: {e}")

    try:
        db[ISSUES_COLLECTION].create_index([("groupId", 1), ("date", 1), ("sourceEventId", 1)])
    except Exception as e:
        logger.warning(f"Index issues compound already exists or skipped: {e}")

    try:
        # direct_reviews: groupId, date (simple and compound)
        db[DIRECT_REVIEWS_COLLECTION].create_index("groupId")
    except Exception as e:
        logger.warning(f"Index direct_reviews.groupId already exists or skipped: {e}")

    try:
        db[DIRECT_REVIEWS_COLLECTION].create_index("date")
    except Exception as e:
        logger.warning(f"Index direct_reviews.date already exists or skipped: {e}")

    try:
        db[DIRECT_REVIEWS_COLLECTION].create_index([("groupId", 1), ("date", 1)])
    except Exception as e:
        logger.warning(f"Index direct_reviews compound already exists or skipped: {e}")

    try:
        # report_checklist: groupId, date (simple indexes)
        db[REPORT_CHECKLIST_COLLECTION].create_index("groupId")
    except Exception as e:
        logger.warning(f"Index report_checklist.groupId already exists or skipped: {e}")

    try:
        db[REPORT_CHECKLIST_COLLECTION].create_index("date")
    except Exception as e:
        logger.warning(f"Index report_checklist.date already exists or skipped: {e}")


def close_client() -> None:
    """Close the active MongoClient."""
    global _mongo_client
    if _mongo_client is not None:
        try:
            _mongo_client.close()
        except Exception:
            pass
        _mongo_client = None
