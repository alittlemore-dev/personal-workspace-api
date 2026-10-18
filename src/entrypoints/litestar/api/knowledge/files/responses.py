from urllib.parse import quote

from litestar.openapi.spec import OpenAPIHeader, Schema
from litestar.openapi.spec.enums import OpenAPIType
from litestar.response import Stream

from core.knowledge.files.enums import KnowledgeFileKind, KnowledgeFileProcessing
from core.knowledge.files.schemas import KnowledgeFileContent
from entrypoints.litestar.openapi_responses import BinaryResponseMetadata
from infra.config.constants import constants


def build_knowledge_file_content_response(*, result: KnowledgeFileContent) -> Stream:
    is_photo = result.file.kind == KnowledgeFileKind.PERSON_PHOTO
    is_inline_image = (
        result.file.processing == KnowledgeFileProcessing.NORMALIZED_RASTER_IMAGE
        and result.file.mime_type == "image/webp"
    )
    safe_ascii_name = "".join(
        character if character.isascii() and (character.isalnum() or character in " ._-") else "_"
        for character in result.file.original_name
    ).strip()
    if not safe_ascii_name:
        safe_ascii_name = "download"
    content_disposition = (
        f'inline; filename="{"photo" if is_photo else "image"}.webp"'
        if is_inline_image
        else (
            f'attachment; filename="{safe_ascii_name}"; '
            f"filename*=UTF-8''{quote(result.file.original_name, safe='')}"
        )
    )
    return Stream(
        result.content,
        media_type=result.file.mime_type if is_inline_image else "application/octet-stream",
        headers={
            constants.knowledge_files.content_disposition_header_name: content_disposition,
            constants.knowledge_files.content_type_options_header_name: (
                constants.knowledge_files.content_type_options_header_value
            ),
            constants.knowledge_files.cache_control_header_name: (
                constants.knowledge_files.no_store_header_value
            ),
        },
    )


KNOWLEDGE_CONTENT_OPENAPI_RESPONSE = BinaryResponseMetadata(
    media_types=("image/webp", "application/octet-stream"),
    description=(
        "Normalized raster images are returned inline as image/webp. All other attachments "
        "are downloaded as application/octet-stream, regardless of their stored mimeType. "
        "Content-Disposition supplies an ASCII filename and a UTF-8 filename* for attachments. "
        "Only the author may read the file."
    ),
    headers={
        "Content-Disposition": OpenAPIHeader(
            description="inline for normalized WebP images; attachment for other files.",
            schema=Schema(
                type=OpenAPIType.STRING,
                examples=[
                    'inline; filename="image.webp"',
                    (
                        'attachment; filename="project-notes.pdf"; '
                        "filename*=UTF-8''project-notes.pdf"
                    ),
                ],
            ),
        ),
        "Cache-Control": OpenAPIHeader(
            description="Private content must not be stored in caches.",
            schema=Schema(
                type=OpenAPIType.STRING,
                examples=[constants.knowledge_files.no_store_header_value],
            ),
        ),
        "X-Content-Type-Options": OpenAPIHeader(
            description="Disable MIME sniffing for uploaded content.",
            schema=Schema(type=OpenAPIType.STRING, examples=["nosniff"]),
        ),
    },
)
