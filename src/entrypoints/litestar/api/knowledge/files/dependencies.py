from datetime import datetime
from typing import Annotated

from backend_sdk import Principal
from backend_sdk.integrations.litestar import AuthContext
from dishka import FromDishka
from dishka.integrations.litestar import inject
from litestar import Request
from litestar.datastructures import State

from core.generators import HexUuidIdGenerator
from core.knowledge.files.enums import KnowledgeFileProcessing
from core.knowledge.files.schemas import (
    DeleteKnowledgeAttachmentParams,
    DeletePersonPhotoParams,
    KnowledgeFileTargetParams,
    RenameKnowledgeAttachmentParams,
    ReplacePersonPhotoParams,
    UploadKnowledgeAttachmentParams,
)
from entrypoints.litestar.api.knowledge.files.schemas import (
    KnowledgeAttachmentUploadRequestSchema,
    KnowledgeEditorImageUploadRequestSchema,
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


@inject
async def provide_replace_person_photo_params(
    person_id: PersonIdPath,
    data: Annotated[
        KnowledgePhotoUploadRequestSchema,
        api_multipart_body(
            title="Person photo upload",
            description="JPEG, PNG, or WebP private person photo.",
            examples=({"file": "photo.png"},),
        ),
    ],
    request: Request[Principal, AuthContext, State],
    id_generator: FromDishka[HexUuidIdGenerator],
    current_datetime: FromDishka[datetime],
) -> ReplacePersonPhotoParams:
    return ReplacePersonPhotoParams(
        data=await data.to_domain_schema(
            file_id=id_generator.get_next(),
            person_id=person_id,
            author_username=request.user.username,
        ),
        current_datetime=current_datetime,
    )


@inject
async def provide_delete_person_photo_params(
    person_id: PersonIdPath,
    request: Request[Principal, AuthContext, State],
    current_datetime: FromDishka[datetime],
) -> DeletePersonPhotoParams:
    return DeletePersonPhotoParams(
        person_id=person_id,
        author_username=request.user.username,
        current_datetime=current_datetime,
    )


@inject
async def provide_upload_attachment_params(
    item_id: KnowledgeItemIdPath,
    data: Annotated[
        KnowledgeAttachmentUploadRequestSchema,
        api_multipart_body(
            title="Knowledge attachment upload",
            description="Private attachment up to 20 MiB.",
            examples=({"name": "Notes", "file": "notes.txt"},),
        ),
    ],
    request: Request[Principal, AuthContext, State],
    id_generator: FromDishka[HexUuidIdGenerator],
    current_datetime: FromDishka[datetime],
) -> UploadKnowledgeAttachmentParams:
    return UploadKnowledgeAttachmentParams(
        data=await data.to_domain_schema(
            file_id=id_generator.get_next(),
            item_id=item_id,
            author_username=request.user.username,
        ),
        processing=KnowledgeFileProcessing.RAW,
        current_datetime=current_datetime,
    )


@inject
async def provide_upload_editor_image_params(
    item_id: KnowledgeItemIdPath,
    data: Annotated[
        KnowledgeEditorImageUploadRequestSchema,
        api_multipart_body(
            title="Knowledge editor image upload",
            description="JPEG, PNG, or WebP private Markdown image.",
            examples=({"file": "diagram.png"},),
        ),
    ],
    request: Request[Principal, AuthContext, State],
    id_generator: FromDishka[HexUuidIdGenerator],
    current_datetime: FromDishka[datetime],
) -> UploadKnowledgeAttachmentParams:
    return UploadKnowledgeAttachmentParams(
        data=await data.to_domain_schema(
            file_id=id_generator.get_next(),
            item_id=item_id,
            author_username=request.user.username,
        ),
        processing=KnowledgeFileProcessing.NORMALIZED_RASTER_IMAGE,
        current_datetime=current_datetime,
    )


@inject
async def provide_rename_attachment_params(
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
    request: Request[Principal, AuthContext, State],
    current_datetime: FromDishka[datetime],
) -> RenameKnowledgeAttachmentParams:
    return RenameKnowledgeAttachmentParams(
        item_id=item_id,
        file_id=file_id,
        author_username=request.user.username,
        data=data.to_domain_schema(),
        current_datetime=current_datetime,
    )


@inject
async def provide_delete_attachment_params(
    item_id: KnowledgeItemIdPath,
    file_id: KnowledgeFileIdPath,
    request: Request[Principal, AuthContext, State],
    current_datetime: FromDishka[datetime],
) -> DeleteKnowledgeAttachmentParams:
    return DeleteKnowledgeAttachmentParams(
        item_id=item_id,
        file_id=file_id,
        author_username=request.user.username,
        current_datetime=current_datetime,
    )


def provide_get_file_content_params(
    file_id: KnowledgeFileIdPath,
    request: Request[Principal, AuthContext, State],
) -> KnowledgeFileTargetParams:
    return KnowledgeFileTargetParams(
        file_id=file_id,
        author_username=request.user.username,
    )
