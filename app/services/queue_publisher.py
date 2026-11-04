"""Queue publisher service for Azure Storage Queue integration."""
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional
from app.config import settings

logger = logging.getLogger(__name__)


class QueuePublisher:
    """Base interface for queue publishing."""

    def publish(self, event: Dict[str, Any]) -> bool:
        raise NotImplementedError


class AzureQueuePublisher(QueuePublisher):
    """Real publisher sending plain UTF-8 JSON messages to Azure Storage Queue."""

    def __init__(self, connection_string: Optional[str] = None, queue_name: Optional[str] = None):
        self.connection_string = connection_string or settings.QUEUE_CONNECTION_STRING
        self.queue_name = queue_name or settings.QUEUE_NAME

    def publish(self, event: Dict[str, Any]) -> bool:
        if not self.connection_string:
            logger.warning("QUEUE_CONNECTION_STRING is not configured. Message skipped.")
            return False

        try:
            from azure.storage.queue import QueueClient

            queue_client = QueueClient.from_connection_string(
                conn_str=self.connection_string,
                queue_name=self.queue_name,
            )
            # Ensure UTF-8 plain JSON message (no base64)
            message_text = json.dumps(event, ensure_ascii=False)
            queue_client.send_message(message_text)
            logger.info(f"Published event {event.get('eventId')} of type {event.get('type')}")
            return True
        except Exception as e:
            logger.error(f"Failed to publish event to Azure Storage Queue: {e}")
            return False


class FakeQueuePublisher(QueuePublisher):
    """In-memory queue publisher for tests."""

    def __init__(self):
        self.published_events: List[Dict[str, Any]] = []
        self.should_fail: bool = False

    def publish(self, event: Dict[str, Any]) -> bool:
        if self.should_fail:
            logger.warning("Simulated queue failure in FakeQueuePublisher.")
            return False
        # Store a copy
        self.published_events.append(dict(event))
        return True

    def clear(self) -> None:
        self.published_events.clear()
        self.should_fail = False


_publisher_instance: Optional[QueuePublisher] = None


def get_publisher() -> QueuePublisher:
    """Get active queue publisher."""
    global _publisher_instance
    if _publisher_instance is None:
        _publisher_instance = AzureQueuePublisher()
    return _publisher_instance


def set_publisher(publisher: Optional[QueuePublisher]) -> None:
    """Override active queue publisher (e.g. for testing)."""
    global _publisher_instance
    _publisher_instance = publisher


def create_queue_event(
    event_type: str,
    course_id: int,
    group_id: int,
    title: str,
    message: str,
) -> Dict[str, Any]:
    """Helper to construct strict queue message conforming to MS3 specification."""
    return {
        "eventId": str(uuid.uuid4()),
        "type": event_type,
        "courseId": int(course_id),
        "groupId": int(group_id),
        "title": str(title),
        "message": str(message),
        "createdAt": int(time.time() * 1000),  # strictly milliseconds
        "source": "ms-analysis",
    }
