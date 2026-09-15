from enum import StrEnum


class PersonListSort(StrEnum):
    UPDATED_NEWEST = "updatedNewest"
    UPDATED_OLDEST = "updatedOldest"
    NAME_ASC = "nameAsc"
    NAME_DESC = "nameDesc"


class PersonRelationshipDirection(StrEnum):
    FORWARD = "forward"
    REVERSE = "reverse"
