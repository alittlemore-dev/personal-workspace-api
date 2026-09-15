from datetime import datetime
from typing import Annotated

from dishka import FromDishka
from litestar import Controller, Request, delete, get, post, put, status_codes
from litestar.response import Stream

from core.files.exceptions import InvalidFileDataError
from core.generators import HexUuidIdGenerator
from core.knowledge.files.clients import (
    KnowledgeFileObjectCleaner,
    KnowledgeFileRollbackRegistrar,
)
from core.knowledge.files.enums import KnowledgeFileProcessing
from core.knowledge.files.use_cases import KnowledgeFilesUseCase
from entrypoints.litestar.api.knowledge.files.post_commit import (
    register_knowledge_object_cleanup,
)
from entrypoints.litestar.api.knowledge.files.responses import (
    build_knowledge_file_content_response,
)
from entrypoints.litestar.api.knowledge.files.schemas import (
    KnowledgeAttachmentUploadRequestSchema,
    KnowledgeEditorImageUploadRequestSchema,
    KnowledgeFileResponseSchema,
    KnowledgeFileUpdateRequestSchema,
    KnowledgePhotoUploadRequestSchema,
)
from entrypoints.litestar.api.parameters import (
    KnowledgeFileIdPath,
    KnowledgeItemIdPath,
    PersonIdPath,
    api_json_body,
    api_multipart_body,
)
from infra.config.constants import constants
from infra.post_commit_actions import PostCommitActions


class KnowledgeFilesApiController(Controller):
    path = "/knowledge"
    tags = ["knowledge files"]
    include_in_schema = False
    response_headers = {
        constants.knowledge_files.cache_control_header_name: (
            constants.knowledge_files.no_store_header_value
        ),
    }

    @put(
        "/people/{person_id:str}/photo",
        description="Replace a private person photo.",
        name="knowledge-person-photo-replace-api-handler",
        status_code=status_codes.HTTP_200_OK,
        request_max_body_size=constants.knowledge_files.photo_request_max_body_size_bytes,
    )
    async def replace_person_photo(  # noqa: PLR0913
        self,
        person_id: PersonIdPath,
        data: Annotated[
            KnowledgePhotoUploadRequestSchema,
            api_multipart_body(
                title="Person photo upload",
                description="JPEG, PNG, or WebP private person photo.",
                examples=({"file": "photo.png"},),
            ),
        ],
        request: Request,
        use_case: FromDishka[KnowledgeFilesUseCase],
        id_generator: FromDishka[HexUuidIdGenerator],
        object_cleaner: FromDishka[KnowledgeFileObjectCleaner],
        post_commit_actions: FromDishka[PostCommitActions],
        rollback_registrar: FromDishka[KnowledgeFileRollbackRegistrar],
        current_datetime: FromDishka[datetime],
    ) -> KnowledgeFileResponseSchema:
        result = await use_case.replace_person_photo(
            params=await data.to_domain_schema(
                file_id=id_generator.get_next(),
                person_id=person_id,
                author_username=request.user.username,
            ),
            rollback_registrar=rollback_registrar,
            current_datetime=current_datetime,
        )
        if result.file is None:
            raise InvalidFileDataError
        register_knowledge_object_cleanup(
            object_names=result.object_names_to_delete,
            object_cleaner=object_cleaner,
            post_commit_actions=post_commit_actions,
        )
        return KnowledgeFileResponseSchema.from_domain_schema(schema=result.file)

    @delete(
        "/people/{person_id:str}/photo",
        description="Delete a private person photo.",
        name="knowledge-person-photo-delete-api-handler",
        status_code=status_codes.HTTP_204_NO_CONTENT,
    )
    async def delete_person_photo(  # noqa: PLR0913
        self,
        person_id: PersonIdPath,
        request: Request,
        use_case: FromDishka[KnowledgeFilesUseCase],
        object_cleaner: FromDishka[KnowledgeFileObjectCleaner],
        post_commit_actions: FromDishka[PostCommitActions],
        current_datetime: FromDishka[datetime],
    ) -> None:
        result = await use_case.delete_person_photo(
            person_id=person_id,
            author_username=request.user.username,
            current_datetime=current_datetime,
        )
        register_knowledge_object_cleanup(
            object_names=result.object_names_to_delete,
            object_cleaner=object_cleaner,
            post_commit_actions=post_commit_actions,
        )

    @post(
        "/items/{item_id:str}/attachments",
        description="Upload a private knowledge item attachment.",
        name="knowledge-attachment-upload-api-handler",
        status_code=status_codes.HTTP_201_CREATED,
        request_max_body_size=constants.knowledge_files.attachment_request_max_body_size_bytes,
    )
    async def upload_attachment(  # noqa: PLR0913
        self,
        item_id: KnowledgeItemIdPath,
        data: Annotated[
            KnowledgeAttachmentUploadRequestSchema,
            api_multipart_body(
                title="Knowledge attachment upload",
                description="Private attachment up to 20 MiB.",
                examples=({"name": "Notes", "file": "notes.txt"},),
            ),
        ],
        request: Request,
        use_case: FromDishka[KnowledgeFilesUseCase],
        id_generator: FromDishka[HexUuidIdGenerator],
        rollback_registrar: FromDishka[KnowledgeFileRollbackRegistrar],
        current_datetime: FromDishka[datetime],
    ) -> KnowledgeFileResponseSchema:
        file = await use_case.upload_attachment(
            params=await data.to_domain_schema(
                file_id=id_generator.get_next(),
                item_id=item_id,
                author_username=request.user.username,
            ),
            processing=KnowledgeFileProcessing.RAW,
            rollback_registrar=rollback_registrar,
            current_datetime=current_datetime,
        )
        return KnowledgeFileResponseSchema.from_domain_schema(schema=file)

    @post(
        "/items/{item_id:str}/editor-images",
        description="Upload a normalized private image for the knowledge Markdown editor.",
        name="knowledge-editor-image-upload-api-handler",
        status_code=status_codes.HTTP_201_CREATED,
        request_max_body_size=constants.knowledge_files.photo_request_max_body_size_bytes,
    )
    async def upload_editor_image(  # noqa: PLR0913
        self,
        item_id: KnowledgeItemIdPath,
        data: Annotated[
            KnowledgeEditorImageUploadRequestSchema,
            api_multipart_body(
                title="Knowledge editor image upload",
                description="JPEG, PNG, or WebP private Markdown image.",
                examples=({"file": "diagram.png"},),
            ),
        ],
        request: Request,
        use_case: FromDishka[KnowledgeFilesUseCase],
        id_generator: FromDishka[HexUuidIdGenerator],
        rollback_registrar: FromDishka[KnowledgeFileRollbackRegistrar],
        current_datetime: FromDishka[datetime],
    ) -> KnowledgeFileResponseSchema:
        file = await use_case.upload_attachment(
            params=await data.to_domain_schema(
                file_id=id_generator.get_next(),
                item_id=item_id,
                author_username=request.user.username,
            ),
            processing=KnowledgeFileProcessing.NORMALIZED_RASTER_IMAGE,
            rollback_registrar=rollback_registrar,
            current_datetime=current_datetime,
        )
        return KnowledgeFileResponseSchema.from_domain_schema(schema=file)

    @put(
        "/items/{item_id:str}/attachments/{file_id:str}",
        description="Rename a private knowledge item attachment.",
        name="knowledge-attachment-rename-api-handler",
        status_code=status_codes.HTTP_200_OK,
    )
    async def rename_attachment(  # noqa: PLR0913
        self,
        item_id: KnowledgeItemIdPath,
        file_id: KnowledgeFileIdPath,
        data: Annotated[
            KnowledgeFileUpdateRequestSchema,
            api_json_body(
                title="Knowledge attachment rename",
                description="Replacement attachment display name.",
                examples=({"name": "Meeting notes"},),
            ),
        ],
        request: Request,
        use_case: FromDishka[KnowledgeFilesUseCase],
        current_datetime: FromDishka[datetime],
    ) -> KnowledgeFileResponseSchema:
        return KnowledgeFileResponseSchema.from_domain_schema(
            schema=await use_case.rename_attachment(
                item_id=item_id,
                file_id=file_id,
                author_username=request.user.username,
                params=data.to_domain_schema(),
                current_datetime=current_datetime,
            ),
        )

    @delete(
        "/items/{item_id:str}/attachments/{file_id:str}",
        description="Delete a private knowledge item attachment.",
        name="knowledge-attachment-delete-api-handler",
        status_code=status_codes.HTTP_204_NO_CONTENT,
    )
    async def delete_attachment(  # noqa: PLR0913
        self,
        item_id: KnowledgeItemIdPath,
        file_id: KnowledgeFileIdPath,
        request: Request,
        use_case: FromDishka[KnowledgeFilesUseCase],
        object_cleaner: FromDishka[KnowledgeFileObjectCleaner],
        post_commit_actions: FromDishka[PostCommitActions],
        current_datetime: FromDishka[datetime],
    ) -> None:
        result = await use_case.delete_attachment(
            item_id=item_id,
            file_id=file_id,
            author_username=request.user.username,
            current_datetime=current_datetime,
        )
        register_knowledge_object_cleanup(
            object_names=result.object_names_to_delete,
            object_cleaner=object_cleaner,
            post_commit_actions=post_commit_actions,
        )

    @get(
        "/files/{file_id:str}/content",
        description="Stream private knowledge file content after an author check.",
        name="knowledge-file-content-api-handler",
        status_code=status_codes.HTTP_200_OK,
    )
    async def get_file_content(
        self,
        file_id: KnowledgeFileIdPath,
        request: Request,
        use_case: FromDishka[KnowledgeFilesUseCase],
    ) -> Stream:
        return build_knowledge_file_content_response(
            result=await use_case.get_file_content(
                file_id=file_id,
                author_username=request.user.username,
            ),
        )
