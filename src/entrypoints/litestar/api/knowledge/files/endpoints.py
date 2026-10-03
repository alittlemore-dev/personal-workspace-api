from typing import Annotated

from dishka import FromDishka
from litestar import Controller, delete, get, post, put, status_codes
from litestar.di import (
    NamedDependency,
    Provide,
)
from litestar.response import Stream

from core.files.exceptions import InvalidFileDataError
from core.knowledge.files.clients import KnowledgeFileObjectCleaner
from core.knowledge.files.schemas import (
    DeleteKnowledgeAttachmentParams,
    DeletePersonPhotoParams,
    KnowledgeFileTargetParams,
    RenameKnowledgeAttachmentParams,
    ReplacePersonPhotoParams,
    UploadKnowledgeAttachmentParams,
)
from core.knowledge.files.use_cases import KnowledgeFilesUseCase
from entrypoints.litestar.api.knowledge.files.dependencies import (
    provide_delete_attachment_params,
    provide_delete_person_photo_params,
    provide_get_file_content_params,
    provide_rename_attachment_params,
    provide_replace_person_photo_params,
    provide_upload_attachment_params,
    provide_upload_editor_image_params,
)
from entrypoints.litestar.api.knowledge.files.post_commit import register_knowledge_object_cleanup
from entrypoints.litestar.api.knowledge.files.responses import build_knowledge_file_content_response
from entrypoints.litestar.api.knowledge.files.schemas import (
    KnowledgeAttachmentUploadRequestSchema,
    KnowledgeEditorImageUploadRequestSchema,
    KnowledgeFileResponseSchema,
    KnowledgePhotoUploadRequestSchema,
)
from entrypoints.litestar.api.parameters import api_multipart_body
from infra.config.constants import constants
from infra.post_commit_actions import PostCommitActions


class KnowledgeFilesApiController(Controller):
    path = "/knowledge"
    tags = ["knowledge files"]
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
        dependencies={
            "params": Provide(provide_replace_person_photo_params),
        },
    )
    async def replace_person_photo(
        self,
        # Litestar requires this handler metadata to decode the dependency's multipart body.
        data: Annotated[  # noqa: ARG002
            KnowledgePhotoUploadRequestSchema,
            api_multipart_body(
                title="Person photo upload",
                description="JPEG, PNG, or WebP private person photo.",
                examples=({"file": "photo.png"},),
            ),
        ],
        use_case: FromDishka[KnowledgeFilesUseCase],
        object_cleaner: FromDishka[KnowledgeFileObjectCleaner],
        post_commit_actions: FromDishka[PostCommitActions],
        params: NamedDependency[ReplacePersonPhotoParams],
    ) -> KnowledgeFileResponseSchema:
        result = await use_case.replace_person_photo(
            params=params,
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
        dependencies={"params": Provide(provide_delete_person_photo_params)},
    )
    async def delete_person_photo(
        self,
        use_case: FromDishka[KnowledgeFilesUseCase],
        object_cleaner: FromDishka[KnowledgeFileObjectCleaner],
        post_commit_actions: FromDishka[PostCommitActions],
        params: NamedDependency[DeletePersonPhotoParams],
    ) -> None:
        result = await use_case.delete_person_photo(
            params=params,
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
        dependencies={
            "params": Provide(provide_upload_attachment_params),
        },
    )
    async def upload_attachment(
        self,
        # Litestar requires this handler metadata to decode the dependency's multipart body.
        data: Annotated[  # noqa: ARG002
            KnowledgeAttachmentUploadRequestSchema,
            api_multipart_body(
                title="Knowledge attachment upload",
                description="Private attachment up to 20 MiB.",
                examples=({"name": "Notes", "file": "notes.txt"},),
            ),
        ],
        use_case: FromDishka[KnowledgeFilesUseCase],
        params: NamedDependency[UploadKnowledgeAttachmentParams],
    ) -> KnowledgeFileResponseSchema:
        file = await use_case.upload_attachment(
            params=params,
        )
        return KnowledgeFileResponseSchema.from_domain_schema(schema=file)

    @post(
        "/items/{item_id:str}/editor-images",
        description="Upload a normalized private image for the knowledge Markdown editor.",
        name="knowledge-editor-image-upload-api-handler",
        status_code=status_codes.HTTP_201_CREATED,
        request_max_body_size=constants.knowledge_files.photo_request_max_body_size_bytes,
        dependencies={
            "params": Provide(provide_upload_editor_image_params),
        },
    )
    async def upload_editor_image(
        self,
        # Litestar requires this handler metadata to decode the dependency's multipart body.
        data: Annotated[  # noqa: ARG002
            KnowledgeEditorImageUploadRequestSchema,
            api_multipart_body(
                title="Knowledge editor image upload",
                description="JPEG, PNG, or WebP private Markdown image.",
                examples=({"file": "diagram.png"},),
            ),
        ],
        use_case: FromDishka[KnowledgeFilesUseCase],
        params: NamedDependency[UploadKnowledgeAttachmentParams],
    ) -> KnowledgeFileResponseSchema:
        file = await use_case.upload_attachment(
            params=params,
        )
        return KnowledgeFileResponseSchema.from_domain_schema(schema=file)

    @put(
        "/items/{item_id:str}/attachments/{file_id:str}",
        description="Rename a private knowledge item attachment.",
        name="knowledge-attachment-rename-api-handler",
        status_code=status_codes.HTTP_200_OK,
        dependencies={"params": Provide(provide_rename_attachment_params)},
    )
    async def rename_attachment(
        self,
        use_case: FromDishka[KnowledgeFilesUseCase],
        params: NamedDependency[RenameKnowledgeAttachmentParams],
    ) -> KnowledgeFileResponseSchema:
        return KnowledgeFileResponseSchema.from_domain_schema(
            schema=await use_case.rename_attachment(
                params=params,
            ),
        )

    @delete(
        "/items/{item_id:str}/attachments/{file_id:str}",
        description="Delete a private knowledge item attachment.",
        name="knowledge-attachment-delete-api-handler",
        status_code=status_codes.HTTP_204_NO_CONTENT,
        dependencies={"params": Provide(provide_delete_attachment_params)},
    )
    async def delete_attachment(
        self,
        use_case: FromDishka[KnowledgeFilesUseCase],
        object_cleaner: FromDishka[KnowledgeFileObjectCleaner],
        post_commit_actions: FromDishka[PostCommitActions],
        params: NamedDependency[DeleteKnowledgeAttachmentParams],
    ) -> None:
        result = await use_case.delete_attachment(
            params=params,
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
        dependencies={"params": Provide(provide_get_file_content_params, sync_to_thread=False)},
    )
    async def get_file_content(
        self,
        use_case: FromDishka[KnowledgeFilesUseCase],
        params: NamedDependency[KnowledgeFileTargetParams],
    ) -> Stream:
        return build_knowledge_file_content_response(
            result=await use_case.get_file_content(
                params=params,
            ),
        )
