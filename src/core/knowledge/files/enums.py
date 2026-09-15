from enum import StrEnum


class KnowledgeFileKind(StrEnum):
    ATTACHMENT = "attachment"
    PERSON_PHOTO = "personPhoto"


class KnowledgeFileProcessing(StrEnum):
    RAW = "raw"
    NORMALIZED_RASTER_IMAGE = "normalizedRasterImage"
