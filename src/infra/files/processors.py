from dataclasses import dataclass
from io import BytesIO
from warnings import catch_warnings, simplefilter

from PIL import Image, ImageOps

from core.files.exceptions import FileImageOptimizationError
from core.files.processors import FileContentProcessor
from core.files.schemas import FileUploadParams
from core.knowledge.files.clients import KnowledgePhotoProcessor
from core.knowledge.files.schemas import (
    KnowledgeFileUploadParams,
    ProcessedKnowledgePhoto,
)

_MIME_TYPE_BY_IMAGE_FORMAT = {
    "GIF": "image/gif",
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


@dataclass(frozen=True, slots=True, kw_only=True)
class AttachmentContentProcessor(FileContentProcessor):
    def process(self, *, params: FileUploadParams) -> FileUploadParams:
        return params


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonPhotoContentProcessor(KnowledgePhotoProcessor):
    max_width_px: int
    max_height_px: int
    max_source_pixels: int
    webp_quality: int
    webp_method: int

    def process(self, *, params: KnowledgeFileUploadParams) -> ProcessedKnowledgePhoto:
        try:
            with catch_warnings():
                simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(params.content)) as source_image:
                    if source_image.width * source_image.height > self.max_source_pixels:
                        raise FileImageOptimizationError
                    source_image.load()
                    detected_mime_type = Image.MIME.get(source_image.format or "")
                    if detected_mime_type != params.mime_type:
                        raise FileImageOptimizationError
                    if bool(getattr(source_image, "is_animated", False)):
                        raise FileImageOptimizationError
                    image = ImageOps.exif_transpose(source_image).copy()
            image.thumbnail(
                (self.max_width_px, self.max_height_px),
                Image.Resampling.LANCZOS,
            )
            if image.mode not in {"RGB", "RGBA"}:
                if image.mode in {"LA", "P"} or "transparency" in image.info:
                    image = image.convert("RGBA")
                else:
                    image = image.convert("RGB")
            output = BytesIO()
            image.save(
                output,
                format="WEBP",
                quality=self.webp_quality,
                method=self.webp_method,
            )
            return ProcessedKnowledgePhoto(
                content=output.getvalue(),
                mime_type="image/webp",
            )
        except (
            OSError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as error:
            raise FileImageOptimizationError from error
