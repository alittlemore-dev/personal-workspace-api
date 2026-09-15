from enum import StrEnum


class CalendarWindow(StrEnum):
    MONTH = "month"
    CURRENT_AND_NEXT_MONTHS = "currentAndNextMonths"


class CalendarEntryKind(StrEnum):
    MEMORABLE_DATE = "memorableDate"
    BIRTHDAY = "birthday"


class CalendarEntryPeriod(StrEnum):
    CURRENT_MONTH = "currentMonth"
    NEXT_MONTH = "nextMonth"
