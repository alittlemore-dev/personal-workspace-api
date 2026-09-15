from pathlib import Path
from typing import Literal

from core.files.enums import FilePurpose
from core.files.schemas import FileRule, FileRules


class PathConstants:
    src_dir: Path = Path(__file__).resolve().parent.parent.parent
    root_dir: Path = src_dir.parent
    backend_env_file: Path = root_dir / ".env"
    repository_env_file: Path = root_dir.parent / ".env"
    env_file: Path = backend_env_file if backend_env_file.exists() else repository_env_file
    infra_dir: Path = src_dir / "infra"
    alembic_dir: Path = infra_dir / "postgresql" / "alembic"


class MinioBucketNamesConstants:
    media: Literal["media"] = "media"
    knowledge_private: Literal["knowledge-private"] = "knowledge-private"


class ValkeyDatabaseConstants:
    response_cache: int = 0
    taskiq_broker: int = 3
    taskiq_results: int = 4


class ValkeyNamespaceConstants:
    cache_warm_operations: str = "CACHE_WARM_OPERATIONS"
    framework: str = "LITESTAR"


class ValkeyConstants:
    databases: ValkeyDatabaseConstants = ValkeyDatabaseConstants()
    namespaces: ValkeyNamespaceConstants = ValkeyNamespaceConstants()
    missing_ttl_seconds: int = -2
    non_expiring_ttl_seconds: int = -1


class ResponseCacheConstants:
    store_name: Literal["litestar_cache"] = "litestar_cache"
    domain_key_separator: Literal[":"] = ":"
    default_ttl_seconds: int = 86_400
    status_scan_batch_size: int = 200
    json_content_type_header_name: bytes = b"content-type"
    json_content_type_header_value: bytes = b"application/json"


class TaskiqConstants:
    queue_name: Literal["personal_workspace_background"] = "personal_workspace_background"
    consumer_group_name: Literal["personal_workspace_background"] = "personal_workspace_background"
    result_prefix: Literal["personal_workspace_taskiq_results"] = (
        "personal_workspace_taskiq_results"
    )
    cache_warm_all_task_name: Literal["cache_warm_all"] = "cache_warm_all"
    cache_warm_domain_task_name: Literal["cache_warm_domain"] = "cache_warm_domain"
    manual_cache_warm_task_name: Literal["manual_cache_warm"] = "manual_cache_warm"
    cache_warm_operation_key_prefix: Literal["operation"] = "operation"
    cache_warm_latest_operation_key: Literal["latest"] = "latest"
    file_orphan_prune_task_name: Literal["file_orphan_prune"] = "file_orphan_prune"


class FilesConstants:
    orphan_cleanup_batch_size: int = 100
    attachment_mime_types: frozenset[str] = frozenset({"*/*"})
    attachment_max_size_bytes: int = 20 * 1024 * 1024
    rules: FileRules = FileRules(
        values={
            FilePurpose.ATTACHMENT: FileRule(
                folder="attachments",
                allowed_mime_types=attachment_mime_types,
                max_size_bytes=attachment_max_size_bytes,
            ),
        },
    )


class KnowledgeFilesConstants:
    attachment_mime_types: frozenset[str] = frozenset({"*/*"})
    photo_mime_types: frozenset[str] = frozenset(
        {"image/jpeg", "image/png", "image/webp"},
    )
    attachment_max_size_bytes: int = 20 * 1024 * 1024
    photo_max_size_bytes: int = 5 * 1024 * 1024
    multipart_overhead_max_size_bytes: int = 64 * 1024
    attachment_request_max_body_size_bytes: int = (
        attachment_max_size_bytes + multipart_overhead_max_size_bytes
    )
    photo_request_max_body_size_bytes: int = (
        photo_max_size_bytes + multipart_overhead_max_size_bytes
    )
    original_name_max_length: int = 255
    mime_type_max_length: int = 255
    photo_max_width_px: int = 2048
    photo_max_height_px: int = 2048
    photo_max_source_pixels: int = 4096 * 4096
    photo_webp_quality: int = 82
    photo_webp_method: int = 6
    stream_chunk_size_bytes: int = 64 * 1024
    attachment_folder: str = "attachments"
    editor_image_folder: str = "editor-images"
    person_photo_folder: str = "person-photos"
    content_disposition_header_name: Literal["Content-Disposition"] = "Content-Disposition"
    content_type_options_header_name: Literal["X-Content-Type-Options"] = "X-Content-Type-Options"
    content_type_options_header_value: Literal["nosniff"] = "nosniff"
    cache_control_header_name: Literal["Cache-Control"] = "Cache-Control"
    no_store_header_value: Literal["no-store"] = "no-store"


class RequestLoggingConstants:
    private_knowledge_path_prefix: Literal["/api/knowledge"] = "/api/knowledge"
    private_knowledge_safe_path: Literal["/api/knowledge/{private}"] = "/api/knowledge/{private}"


class ResumeExportConstants:
    fonts_dir: Path = PathConstants.infra_dir / "resume_export" / "fonts"
    font_regular_path: Path = fonts_dir / "NotoSans-Regular.ttf"
    font_bold_path: Path = fonts_dir / "NotoSans-Bold.ttf"
    font_license_path: Path = fonts_dir / "OFL.txt"
    font_regular_name: Literal["NotoSans"] = "NotoSans"
    font_bold_name: Literal["NotoSans-Bold"] = "NotoSans-Bold"
    content_disposition_header_name: Literal["Content-Disposition"] = "Content-Disposition"
    pdf_media_type: Literal["application/pdf"] = "application/pdf"
    docx_media_type: Literal[
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ] = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    pdf_extension: Literal["pdf"] = "pdf"
    docx_extension: Literal["docx"] = "docx"
    pdf_horizontal_margin_mm: int = 17
    pdf_vertical_margin_mm: int = 14
    pdf_title_font_size: int = 16
    pdf_role_font_size: int = 10
    pdf_contact_font_size: int = 8
    pdf_section_font_size: int = 10
    pdf_item_title_font_size: int = 9
    pdf_body_font_size: int = 8
    pdf_title_leading: int = 19
    pdf_role_leading: int = 13
    pdf_contact_leading: int = 10
    pdf_section_leading: int = 12
    pdf_body_leading: int = 11
    word_font_name: Literal["Arial"] = "Arial"
    word_margin_inches: float = 0.55
    word_title_font_size_pt: int = 16
    word_role_font_size_pt: int = 10
    word_contact_font_size_pt: int = 8
    word_section_font_size_pt: int = 10
    word_item_title_font_size_pt: int = 9
    word_body_font_size_pt: int = 9
    word_name_style_id: Literal["ResumeName"] = "ResumeName"
    word_role_style_id: Literal["ResumeRole"] = "ResumeRole"
    word_contact_style_id: Literal["ResumeContact"] = "ResumeContact"
    word_section_style_id: Literal["ResumeSection"] = "ResumeSection"
    word_item_title_style_id: Literal["ResumeItemTitle"] = "ResumeItemTitle"
    word_body_style_id: Literal["ResumeBody"] = "ResumeBody"


class SearchConstants:
    min_trigram_fuzzy_query_length: int = 6


class ApiValidationConstants:
    short_text_max_length: int = 255
    url_max_length: int = 2_048
    email_max_length: int = 254
    resume_long_text_max_length: int = 10_000
    knowledge_description_max_length: int = 100_000
    knowledge_relationship_note_max_length: int = 10_000


class AuthConstants:
    argon2id_hash_prefix: Literal["$argon2id$"] = "$argon2id$"


class Constants:
    path: PathConstants = PathConstants()
    minio_buckets: MinioBucketNamesConstants = MinioBucketNamesConstants()
    valkey: ValkeyConstants = ValkeyConstants()
    response_cache: ResponseCacheConstants = ResponseCacheConstants()
    taskiq: TaskiqConstants = TaskiqConstants()
    files: FilesConstants = FilesConstants()
    knowledge_files: KnowledgeFilesConstants = KnowledgeFilesConstants()
    request_logging: RequestLoggingConstants = RequestLoggingConstants()
    resume_export: ResumeExportConstants = ResumeExportConstants()
    search: SearchConstants = SearchConstants()
    api_validation: ApiValidationConstants = ApiValidationConstants()
    auth: AuthConstants = AuthConstants()


constants = Constants()
