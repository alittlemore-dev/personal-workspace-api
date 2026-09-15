from enum import StrEnum


class KnowledgeDateListSort(StrEnum):
    DATE_ASC = "dateAsc"
    DATE_DESC = "dateDesc"
    UPDATED_NEWEST = "updatedNewest"
    UPDATED_OLDEST = "updatedOldest"
    NAME_ASC = "nameAsc"
    NAME_DESC = "nameDesc"
