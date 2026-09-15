from datetime import datetime

import pytest_asyncio
from httpx import codes

from core.files.enums import FilePurpose
from core.files.schemas import FileUpdateParams, FileUploadParams
from tests.test_cases import ApiTestCase


class TestFilesApi(ApiTestCase):
    @pytest_asyncio.fixture(autouse=True)
    async def setup(self) -> None:
        self.use_case = await self.container.get_file_service()
        self.id_generator = await self.container.get_hex_uuid_id_generator()
        self.file_id = self.id_generator.get_next()
        file = self.factory.core.stored_file(
            file_id=self.file_id,
            purpose=FilePurpose.ATTACHMENT,
            relative_path="attachments/file.pdf",
            mime_type="application/pdf",
            name="Attachment",
            original_name="file.pdf",
        )
        self.file_read = self.factory.core.file_read(
            file=file,
            access_url="https://cdn.example.test/media/attachments/file.pdf",
            markdown_url=(
                f"https://cdn.example.test/media/attachments/file.pdf#fileId={self.file_id}"
            ),
        )

    def test_upload_maps_current_attachment_contract(self) -> None:
        self.use_case.upload_file.return_value = self.file_read

        response = self.api.post_file(
            purpose=FilePurpose.ATTACHMENT.value,
            name="Attachment",
            filename="file.pdf",
            content=b"data",
            content_type="application/pdf",
        )

        self.asserts.status(response=response, expected_status=codes.CREATED)
        assert response.json()["purpose"] == "attachment"
        assert response.json()["id"] == self.file_id
        call = self.use_case.upload_file.await_args.kwargs
        assert call["params"] == FileUploadParams(
            id=self.file_id,
            purpose=FilePurpose.ATTACHMENT,
            name="Attachment",
            original_name="file.pdf",
            mime_type="application/pdf",
            content=b"data",
        )
        assert isinstance(call["current_datetime"], datetime)

    def test_list_maps_required_attachment_filter(self) -> None:
        self.use_case.list_files.return_value = [self.file_read]

        response = self.api.get_files(purpose=FilePurpose.ATTACHMENT.value)

        self.asserts.status(response=response, expected_status=codes.OK)
        assert response.json()["files"][0]["id"] == self.file_id
        self.use_case.list_files.assert_awaited_once_with(purpose=FilePurpose.ATTACHMENT)

    def test_get_and_update_map_file_id_and_metadata(self) -> None:
        self.use_case.get_file.return_value = self.file_read
        self.use_case.update_file.return_value = self.file_read

        detail_response = self.api.get_file(file_id=self.file_id)
        update_response = self.api.put_file(
            file_id=self.file_id,
            name="Updated attachment",
        )

        self.asserts.status(response=detail_response, expected_status=codes.OK)
        self.asserts.status(response=update_response, expected_status=codes.OK)
        self.use_case.get_file.assert_awaited_once_with(file_id=self.file_id)
        update_call = self.use_case.update_file.await_args.kwargs
        assert update_call["file_id"] == self.file_id
        assert update_call["params"] == FileUpdateParams(name="Updated attachment")
        assert isinstance(update_call["current_datetime"], datetime)

    def test_delete_maps_file_id(self) -> None:
        response = self.api.delete_file(file_id=self.file_id)

        self.asserts.status(response=response, expected_status=codes.NO_CONTENT)
        self.use_case.delete_file.assert_awaited_once_with(file_id=self.file_id)
