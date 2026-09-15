from collections.abc import Iterable

import pytest
from verbose_http_exceptions.exc.base import BaseVerboseHTTPException

from core.cache_tools.exceptions import CacheWarmOperationNotFoundError
from core.exceptions import EntryNotFoundError
from core.files.exceptions import (
    ContentTypeNotAllowedError,
    FileClientInternalError,
    FileInUseError,
    FileNameInvalidError,
    FilePurposeNotAllowedError,
    FileSizeTooLargeError,
    InvalidFileDataError,
    NamespaceNotAllowedError,
)
from core.knowledge.exceptions import (
    InvalidKnowledgeDataError,
    KnowledgeConflictError,
    KnowledgeDateNotFoundError,
    KnowledgeFileNotFoundError,
    KnowledgeItemNotFoundError,
    KnowledgeTagNotFoundError,
    PersonNotFoundError,
    PersonRelationshipNotFoundError,
    PersonRelationshipTypeNotFoundError,
)
from core.resumes.exceptions import ResumeNotFoundError


def core_exception_classes() -> Iterable[type[Exception]]:
    return (
        EntryNotFoundError,
        CacheWarmOperationNotFoundError,
        InvalidFileDataError,
        ContentTypeNotAllowedError,
        FileSizeTooLargeError,
        NamespaceNotAllowedError,
        FilePurposeNotAllowedError,
        FileNameInvalidError,
        FileClientInternalError,
        FileInUseError,
        KnowledgeItemNotFoundError,
        PersonNotFoundError,
        KnowledgeDateNotFoundError,
        KnowledgeTagNotFoundError,
        PersonRelationshipTypeNotFoundError,
        PersonRelationshipNotFoundError,
        KnowledgeFileNotFoundError,
        InvalidKnowledgeDataError,
        KnowledgeConflictError,
        ResumeNotFoundError,
    )


@pytest.mark.parametrize("exception_class", core_exception_classes())
def test_core_exception_does_not_inherit_http_exception(
    exception_class: type[Exception],
) -> None:
    assert not issubclass(exception_class, BaseVerboseHTTPException)
