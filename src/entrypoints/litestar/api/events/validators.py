import re
from datetime import UTC, date, datetime

from core.events.enums import EventFrequency
from core.events.exceptions import InvalidEventDataError

UTC_INSTANT_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_event_interval(
    *,
    all_day: bool,
    start: str,
    end: str,
) -> tuple[date | datetime, date | datetime]:
    if all_day:
        if not DATE_PATTERN.fullmatch(start) or not DATE_PATTERN.fullmatch(end):
            raise InvalidEventDataError
        return date.fromisoformat(start), date.fromisoformat(end)
    if not UTC_INSTANT_PATTERN.fullmatch(start) or not UTC_INSTANT_PATTERN.fullmatch(end):
        raise InvalidEventDataError
    return datetime.fromisoformat(start).astimezone(UTC), datetime.fromisoformat(end).astimezone(
        UTC,
    )


def validate_event_interval(
    *,
    all_day: bool,
    start: str,
    end: str,
    frequency: EventFrequency,
    until_date: date | None,
) -> None:
    try:
        parsed_start, parsed_end = parse_event_interval(all_day=all_day, start=start, end=end)
    except (InvalidEventDataError, ValueError) as error:
        message = "Invalid event time or recurrence"
        raise ValueError(message) from error
    if parsed_start >= parsed_end or (frequency == EventFrequency.NONE and until_date is not None):
        message = "Invalid event time or recurrence"
        raise ValueError(message)
