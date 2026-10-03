from enum import StrEnum


class ResumeCurrentStatusEnum(StrEnum):
    NOT_SET = "notSet"
    CURRENT = "current"
    NOT_CURRENT = "notCurrent"


class ResumeExportFormatEnum(StrEnum):
    PDF = "pdf"
    DOCX = "docx"


class ResumeThemeEnum(StrEnum):
    SIMPLE = "simple"
    ACCENT = "accent"


class ResumeDateFormatEnum(StrEnum):
    MONTH_YEAR = "monthYear"
    MONTH_YEAR_NUMERIC = "monthYearNumeric"
    FULL_DATE = "fullDate"
    YEAR = "year"
