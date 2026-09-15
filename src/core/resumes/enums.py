from enum import StrEnum


class ResumeCurrentStatusEnum(StrEnum):
    NOT_SET = "notSet"
    CURRENT = "current"
    NOT_CURRENT = "notCurrent"


class ResumeExportFormatEnum(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
