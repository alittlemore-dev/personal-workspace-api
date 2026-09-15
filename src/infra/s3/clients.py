import json
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import dataclass
from http import HTTPStatus
from io import BytesIO
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError
from types_aiobotocore_s3.client import S3Client
from types_aiobotocore_s3.type_defs import CORSConfigurationTypeDef

from core.files.clients import FileClient
from core.files.exceptions import FileClientInternalError, NamespaceNotAllowedError
from core.files.schemas import FileUploadResult
from core.files.types import Namespace
from core.knowledge.files.clients import (
    KnowledgeFileClient,
    KnowledgeFileObjectCleaner,
)
from infra.config.loggers import logger
from infra.config.settings import settings


@dataclass(frozen=True, kw_only=True, slots=True)
class S3ClientBundle:
    internal: S3Client
    public: S3Client


@dataclass(kw_only=True)
class S3FileClient(FileClient):
    clients: S3ClientBundle

    @staticmethod
    def create_bucket_policy(bucket_name: str) -> dict[str, Any]:
        return {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": "*"},
                    "Action": ["s3:GetBucketLocation", "s3:ListBucket"],
                    "Resource": f"arn:aws:s3:::{bucket_name}",
                },
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": "*"},
                    "Action": "s3:GetObject",
                    "Resource": f"arn:aws:s3:::{bucket_name}/*",
                },
            ],
        }

    @staticmethod
    def create_bucket_cors(allowed_origin: str, max_age_seconds: int) -> CORSConfigurationTypeDef:
        return {
            "CORSRules": [
                {
                    "AllowedHeaders": ["*"],
                    "AllowedMethods": ["GET"],
                    "AllowedOrigins": [allowed_origin],
                    "ExposeHeaders": ["ETag"],
                    "MaxAgeSeconds": max_age_seconds,
                },
            ],
        }

    @staticmethod
    def _ensure_valid_namespace(namespace: str) -> Namespace:
        if namespace != "media":
            logger.error("Passed incorrect namespace:", bucket_name=namespace)
            raise NamespaceNotAllowedError(namespace=namespace)
        return namespace  # type: ignore[return-value]

    async def ensure_namespace_exists(self, namespace: str) -> None:
        logger.info("Ensuring bucket exists", bucket_name=namespace)
        if not await self._bucket_exists(bucket_name=namespace):
            await self.clients.internal.create_bucket(Bucket=namespace)
            logger.info("Bucket created", bucket_name=namespace)
        await self.clients.internal.put_bucket_policy(
            Bucket=namespace,
            Policy=json.dumps(self.create_bucket_policy(bucket_name=namespace)),
        )
        try:
            await self.clients.internal.put_bucket_cors(
                Bucket=namespace,
                CORSConfiguration=self.create_bucket_cors(
                    allowed_origin=settings.app.public_origin,
                    max_age_seconds=settings.minio.cors_max_age_seconds,
                ),
            )
        except ClientError as exc:
            if not self._is_operation_not_implemented(exc):
                raise
            logger.warning(
                "S3 bucket CORS setup is not supported by the storage service",
                bucket_name=namespace,
            )
        logger.info("Bucket policy set and bucket CORS setup attempted", bucket_name=namespace)

    async def upload_file(
        self,
        file_data: BytesIO,
        object_name: str,
        namespace: str,
        content_type: str,
    ) -> FileUploadResult:
        _namespace = self._ensure_valid_namespace(namespace)
        logger.info("Uploading file", bucket_name=_namespace, object_name=object_name)
        object_bytes = file_data.getvalue()
        try:
            await self.ensure_namespace_exists(namespace=_namespace)
            await self.clients.internal.put_object(
                Bucket=_namespace,
                Key=object_name,
                Body=object_bytes,
                ContentType=content_type,
            )
            upload_result = FileUploadResult(
                url=self.get_access_url(object_name=object_name, namespace=_namespace),
                bucket=_namespace,
                object_name=object_name,
                size=len(object_bytes),
            )
        except ClientError as e:
            logger.exception(
                "S3 upload failed",
                bucket_name=_namespace,
                object_name=object_name,
            )
            raise FileClientInternalError(message="File upload failed") from e
        else:
            logger.info(
                "File uploaded successfully",
                result=upload_result,
            )
            return upload_result

    async def delete_file(self, object_name: str, namespace: str) -> None:
        _namespace = self._ensure_valid_namespace(namespace)
        logger.info("Deleting file", bucket_name=_namespace, object_name=object_name)
        try:
            await self.clients.internal.delete_object(Bucket=_namespace, Key=object_name)
        except (BotoCoreError, ClientError) as e:
            logger.exception(
                "S3 delete failed",
                bucket_name=_namespace,
                object_name=object_name,
            )
            raise FileClientInternalError(message="File delete failed") from e

    async def init_storage(self) -> None:
        logger.info("Initializing storage")
        await self.ensure_namespace_exists(namespace="media")
        logger.info("Storage initialized successfully")

    def get_access_url(self, object_name: str, namespace: str) -> str:
        _namespace = self._ensure_valid_namespace(namespace)
        return settings.minio.get_object_url(bucket=_namespace, object_path=object_name)

    async def _bucket_exists(self, bucket_name: str) -> bool:
        try:
            await self.clients.internal.head_bucket(Bucket=bucket_name)
        except ClientError as exc:
            if self._is_bucket_not_found(exc):
                return False
            raise
        return True

    @staticmethod
    def _is_bucket_not_found(exc: ClientError) -> bool:
        error_matches = False
        status_matches = False
        with suppress(KeyError):
            error_matches = str(exc.response["Error"]["Code"]) in {
                "404",
                "NoSuchBucket",
                "NotFound",
            }
        with suppress(KeyError):
            status_matches = (
                exc.response["ResponseMetadata"]["HTTPStatusCode"] == HTTPStatus.NOT_FOUND
            )
        return error_matches or status_matches

    @staticmethod
    def _is_operation_not_implemented(exc: ClientError) -> bool:
        with suppress(KeyError):
            return str(exc.response["Error"]["Code"]) == "NotImplemented"
        return False


@dataclass(kw_only=True)
class S3KnowledgeFileClient(KnowledgeFileClient, KnowledgeFileObjectCleaner):
    internal_client: S3Client
    bucket_name: str
    stream_chunk_size_bytes: int

    async def ensure_namespace_exists(self) -> None:
        if not await self.bucket_exists():
            await self.internal_client.create_bucket(Bucket=self.bucket_name)
            logger.info("Private knowledge bucket created", bucket_name=self.bucket_name)
        for operation in (
            self.internal_client.delete_bucket_policy,
            self.internal_client.delete_bucket_cors,
        ):
            try:
                await operation(Bucket=self.bucket_name)
            except ClientError as error:
                if not self.operation_is_absent_or_unsupported(error=error):
                    raise
        logger.info(
            "Private knowledge bucket access policy verified",
            bucket_name=self.bucket_name,
        )

    async def upload_file(
        self,
        *,
        content: bytes,
        object_name: str,
        content_type: str,
    ) -> None:
        try:
            await self.ensure_namespace_exists()
            await self.internal_client.put_object(
                Bucket=self.bucket_name,
                Key=object_name,
                Body=content,
                ContentType=content_type,
            )
        except ClientError as error:
            logger.exception(
                "Private knowledge file upload failed",
                bucket_name=self.bucket_name,
            )
            raise FileClientInternalError(message="Private file upload failed") from error

    async def stream_file(self, *, object_name: str) -> AsyncIterator[bytes]:
        try:
            response = await self.internal_client.get_object(
                Bucket=self.bucket_name,
                Key=object_name,
            )
        except ClientError as error:
            logger.exception(
                "Private knowledge file read failed",
                bucket_name=self.bucket_name,
            )
            raise FileClientInternalError(message="Private file read failed") from error
        body = response["Body"]
        try:
            while chunk := await body.read(self.stream_chunk_size_bytes):
                yield chunk
        except ClientError as error:
            logger.exception(
                "Private knowledge file stream failed",
                bucket_name=self.bucket_name,
            )
            raise FileClientInternalError(message="Private file stream failed") from error
        finally:
            body.close()

    async def init_storage(self) -> None:
        await self.ensure_namespace_exists()

    async def cleanup_objects(self, *, object_names: tuple[str, ...]) -> None:
        failed_count = 0
        for object_name in object_names:
            try:
                await self.internal_client.delete_object(
                    Bucket=self.bucket_name,
                    Key=object_name,
                )
            except Exception:  # noqa: BLE001
                failed_count += 1
        if failed_count:
            logger.error(
                "Private knowledge object cleanup incomplete",
                bucket_name=self.bucket_name,
                failed_count=failed_count,
                total_count=len(object_names),
            )

    async def bucket_exists(self) -> bool:
        try:
            await self.internal_client.head_bucket(Bucket=self.bucket_name)
        except ClientError as error:
            if self.bucket_is_not_found(error=error):
                return False
            raise
        return True

    @staticmethod
    def bucket_is_not_found(*, error: ClientError) -> bool:
        error_matches = False
        status_matches = False
        with suppress(KeyError):
            error_matches = str(error.response["Error"]["Code"]) in {
                "404",
                "NoSuchBucket",
                "NotFound",
            }
        with suppress(KeyError):
            status_matches = (
                error.response["ResponseMetadata"]["HTTPStatusCode"] == HTTPStatus.NOT_FOUND
            )
        return error_matches or status_matches

    @staticmethod
    def operation_is_absent_or_unsupported(*, error: ClientError) -> bool:
        with suppress(KeyError):
            return str(error.response["Error"]["Code"]) in {
                "404",
                "NoSuchBucketPolicy",
                "NoSuchCORSConfiguration",
                "NotFound",
                "NotImplemented",
            }
        return False
