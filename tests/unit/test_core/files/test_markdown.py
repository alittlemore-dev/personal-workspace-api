from core.files.markdown import extract_file_ids_from_markdown


def test_extract_file_ids_from_markdown_deduplicates_supported_url_markers() -> None:
    content = (
        "![first](/api/files/one?fileId=file_one) "
        "[second](/api/files/two#fileId=file-two) "
        "[duplicate](/api/files/one?size=small&fileId=file_one) "
        "[unrelated](/api/files/three?file=ignored)"
    )

    assert extract_file_ids_from_markdown(content) == frozenset({"file_one", "file-two"})
