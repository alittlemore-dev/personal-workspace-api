from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from mimetypes import guess_extension
from pathlib import PurePath

from core.files.exceptions import (
    ContentTypeNotAllowedError,
    FileNameInvalidError,
    FileSizeTooLargeError,
    InvalidFileDataError,
)
from core.files.types import Namespace
from core.knowledge.files.enums import KnowledgeFileKind, KnowledgeFileProcessing


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeFileRule:
    folder: str
    allowed_mime_types: frozenset[str]
    max_size_bytes: int
    original_name_max_length: int
    mime_type_max_length: int


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeFileRules:
    values: Mapping[KnowledgeFileKind, KnowledgeFileRule]

    def require(self, *, kind: KnowledgeFileKind) -> KnowledgeFileRule:
        return self.values[kind]


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeFileServiceConfig:
    namespace: Namespace
    rules: KnowledgeFileRules
    normalized_raster_image_rules: KnowledgeFileRules


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeFile:
    id: str
    item_id: str
    author_username: str
    kind: KnowledgeFileKind
    processing: KnowledgeFileProcessing
    relative_path: str
    mime_type: str
    size_bytes: int
    name: str
    original_name: str
    original_sha256: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeFileUploadParams:
    id: str
    item_id: str
    author_username: str
    kind: KnowledgeFileKind
    name: str
    original_name: str
    mime_type: str
    content: bytes

    @property
    def size_bytes(self) -> int:
        return len(self.content)

    @property
    def file_extension(self) -> str:
        return guess_extension(self.mime_type) or PurePath(self.original_name).suffix

    def validate(self, *, rule: KnowledgeFileRule) -> None:
        if not self.name.strip() or not self.original_name.strip():
            raise FileNameInvalidError
        if len(self.original_name) > rule.original_name_max_length:
            raise FileNameInvalidError
        if "\r" in self.mime_type or "\n" in self.mime_type or not self.mime_type.strip():
            raise InvalidFileDataError
        if len(self.mime_type) > rule.mime_type_max_length:
            raise InvalidFileDataError
        if "*/*" not in rule.allowed_mime_types and self.mime_type not in rule.allowed_mime_types:
            raise ContentTypeNotAllowedError(content_type=self.mime_type)
        if self.size_bytes > rule.max_size_bytes:
            raise FileSizeTooLargeError(
                size_bytes=self.size_bytes,
                max_size_bytes=rule.max_size_bytes,
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class ProcessedKnowledgePhoto:
    content: bytes
    mime_type: str


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeFileUpdateParams:
    name: str

    def validate(self) -> None:
        if not self.name.strip():
            raise FileNameInvalidError


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeFileContent:
    file: KnowledgeFile
    content: AsyncIterator[bytes]


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeFileMutationResult:
    file: KnowledgeFile | None
    object_names_to_delete: tuple[str, ...]
