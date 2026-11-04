"""Script to send a test event to Azure Storage Queue according to MS3 format."""
import argparse
import json
import logging
import sys
from app.config import settings
from app.services.queue_publisher import create_queue_event, AzureQueuePublisher

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("send_test_event")


def send_test_event(
    event_type: str = "FEEDBACK_PUBLISHED",
    course_id: int = 1,
    group_id: int = 1,
    title: str = "Prueba de evento",
    message: str = "Mensaje de prueba generado por script send_test_event.py",
) -> bool:
    """Build and publish an event to Azure Storage Queue."""
    if event_type not in ("FEEDBACK_PUBLISHED", "ISSUE_DETECTED"):
        logger.error(f"Invalid event type: {event_type}. Must be FEEDBACK_PUBLISHED or ISSUE_DETECTED.")
        return False

    event = create_queue_event(
        event_type=event_type,
        course_id=course_id,
        group_id=group_id,
        title=title,
        message=message,
    )

    logger.info("Generated event payload for MS3:")
    print(json.dumps(event, indent=2, ensure_ascii=False))

    if not settings.QUEUE_CONNECTION_STRING:
        logger.warning(
            "QUEUE_CONNECTION_STRING is not set in environment. "
            "Event payload printed above without sending to Azure."
        )
        return True

    publisher = AzureQueuePublisher()
    success = publisher.publish(event)
    if success:
        logger.info("Event successfully delivered to Azure Storage Queue!")
    else:
        logger.error("Failed to deliver event to Azure Storage Queue.")
    return success


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send test event to RevisaTEC queue.")
    parser.add_argument(
        "--type",
        choices=["FEEDBACK_PUBLISHED", "ISSUE_DETECTED"],
        default="FEEDBACK_PUBLISHED",
        help="Event type",
    )
    parser.add_argument("--course-id", type=int, default=1, help="Course ID")
    parser.add_argument("--group-id", type=int, default=1, help="Group ID")
    parser.add_argument("--title", type=str, default="Retroalimentación publicada", help="Event title")
    parser.add_argument("--message", type=str, default="Se publicó la retroalimentación de Grupo 1", help="Event message")

    args = parser.parse_args()

    ok = send_test_event(
        event_type=args.type,
        course_id=args.course_id,
        group_id=args.group_id,
        title=args.title,
        message=args.message,
    )
    sys.exit(0 if ok else 1)
