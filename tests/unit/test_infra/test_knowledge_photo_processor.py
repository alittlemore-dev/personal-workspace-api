from io import BytesIO
from unittest.mock import patch

import pytest
from PIL import Image

from core.files.exceptions import FileImageOptimizationError
from core.knowledge.files.enums import KnowledgeFileKind
from core.knowledge.files.schemas import KnowledgeFileUploadParams
from infra.files.processors import PersonPhotoContentProcessor


def image_bytes(*, image_format: str, size: tuple[int, int] = (20, 10)) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, color=(20, 40, 60)).save(output, format=image_format)
    return output.getvalue()


class TestPersonPhotoContentProcessor:
    def setup_method(self) -> None:
        self.processor = PersonPhotoContentProcessor(
            max_width_px=8,
            max_height_px=8,
            max_source_pixels=200,
            webp_quality=82,
            webp_method=6,
        )

    @pytest.mark.parametrize(
        ("image_format", "mime_type"),
        [
            ("PNG", "image/png"),
            ("JPEG", "image/jpeg"),
            ("WEBP", "image/webp"),
        ],
    )
    def test_normalizes_supported_static_image_at_source_pixel_limit(
        self,
        image_format: str,
        mime_type: str,
    ) -> None:
        result = self.processor.process(
            params=KnowledgeFileUploadParams(
                id="1" * 32,
                item_id="2" * 32,
                author_username="owner",
                kind=KnowledgeFileKind.PERSON_PHOTO,
                name="Photo",
                original_name=f"photo.{image_format.lower()}",
                mime_type=mime_type,
                content=image_bytes(image_format=image_format),
            ),
        )

        assert result.mime_type == "image/webp"
        with Image.open(BytesIO(result.content)) as image:
            assert image.format == "WEBP"
            assert image.width <= 8
            assert image.height <= 8

    def test_rejects_source_pixel_count_above_limit_before_loading_pixels(self) -> None:
        params = KnowledgeFileUploadParams(
            id="1" * 32,
            item_id="2" * 32,
            author_username="owner",
            kind=KnowledgeFileKind.PERSON_PHOTO,
            name="Photo",
            original_name="photo.png",
            mime_type="image/png",
            content=image_bytes(image_format="PNG", size=(201, 1)),
        )

        with (
            patch.object(
                Image.Image,
                "load",
                side_effect=AssertionError("oversized source pixels were loaded"),
            ) as load,
            pytest.raises(FileImageOptimizationError),
        ):
            self.processor.process(params=params)

        load.assert_not_called()

    def test_rejects_declared_mime_mismatch(self) -> None:
        with pytest.raises(FileImageOptimizationError):
            self.processor.process(
                params=KnowledgeFileUploadParams(
                    id="1" * 32,
                    item_id="2" * 32,
                    author_username="owner",
                    kind=KnowledgeFileKind.PERSON_PHOTO,
                    name="Photo",
                    original_name="photo.jpg",
                    mime_type="image/jpeg",
                    content=image_bytes(image_format="PNG"),
                ),
            )

    def test_rejects_animated_webp(self) -> None:
        output = BytesIO()
        frames = [
            Image.new("RGB", (4, 4), color=(255, 0, 0)),
            Image.new("RGB", (4, 4), color=(0, 255, 0)),
        ]
        frames[0].save(
            output,
            format="WEBP",
            save_all=True,
            append_images=frames[1:],
            duration=100,
            loop=0,
        )

        with pytest.raises(FileImageOptimizationError):
            self.processor.process(
                params=KnowledgeFileUploadParams(
                    id="1" * 32,
                    item_id="2" * 32,
                    author_username="owner",
                    kind=KnowledgeFileKind.PERSON_PHOTO,
                    name="Photo",
                    original_name="photo.webp",
                    mime_type="image/webp",
                    content=output.getvalue(),
                ),
            )
