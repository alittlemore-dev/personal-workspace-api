from core.files.enums import FilePurpose
from core.files.schemas import FileUploadParams
from infra.files.processors import AttachmentContentProcessor


def test_attachment_processor_preserves_untrusted_bytes_for_later_download_policy() -> None:
    params = FileUploadParams(
        id="file-id",
        purpose=FilePurpose.ATTACHMENT,
        name="Attachment",
        original_name="attachment.bin",
        mime_type="application/octet-stream",
        content=b"untrusted attachment bytes",
    )

    result = AttachmentContentProcessor().process(params=params)

    assert result is params
