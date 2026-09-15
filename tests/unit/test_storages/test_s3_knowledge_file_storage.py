from unittest.mock import AsyncMock, Mock

import pytest
from botocore.exceptions import ClientError

from infra.s3.clients import S3KnowledgeFileClient


def client_error(*, code: str, operation: str) -> ClientError:
    return ClientError(
        error_response={
            "Error": {"Code": code, "Message": code},
            "ResponseMetadata": {"HTTPStatusCode": 404},
        },
        operation_name=operation,
    )


class TestS3KnowledgeFileClient:
    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        self.s3 = Mock()
        self.client = S3KnowledgeFileClient(
            internal_client=self.s3,
            bucket_name="knowledge-private",
            stream_chunk_size_bytes=4,
        )

    async def test_init_creates_private_bucket_and_removes_policy_and_cors(self) -> None:
        self.s3.head_bucket = AsyncMock(
            side_effect=client_error(code="NoSuchBucket", operation="HeadBucket"),
        )
        self.s3.create_bucket = AsyncMock()
        self.s3.delete_bucket_policy = AsyncMock(
            side_effect=client_error(
                code="NoSuchBucketPolicy",
                operation="DeleteBucketPolicy",
            ),
        )
        self.s3.delete_bucket_cors = AsyncMock(
            side_effect=client_error(
                code="NoSuchCORSConfiguration",
                operation="DeleteBucketCors",
            ),
        )

        await self.client.init_storage()

        self.s3.create_bucket.assert_awaited_once_with(Bucket="knowledge-private")
        self.s3.delete_bucket_policy.assert_awaited_once_with(Bucket="knowledge-private")
        self.s3.delete_bucket_cors.assert_awaited_once_with(Bucket="knowledge-private")
        assert "put_bucket_policy" not in {call[0] for call in self.s3.method_calls}
        assert "put_bucket_cors" not in {call[0] for call in self.s3.method_calls}

    async def test_stream_yields_multiple_chunks_and_always_closes_body(self) -> None:
        body = Mock()
        body.read = AsyncMock(side_effect=[b"one", b"two", b""])
        body.close = Mock()
        self.s3.get_object = AsyncMock(return_value={"Body": body})

        chunks = [
            chunk async for chunk in self.client.stream_file(object_name="attachments/private.bin")
        ]

        assert chunks == [b"one", b"two"]
        assert body.read.await_count == 3
        body.close.assert_called_once_with()

    async def test_cleanup_swallows_object_failures(self) -> None:
        self.s3.delete_object = AsyncMock(
            side_effect=[
                client_error(code="InternalError", operation="DeleteObject"),
                None,
            ],
        )

        await self.client.cleanup_objects(object_names=("one", "two"))

        assert self.s3.delete_object.await_count == 2
