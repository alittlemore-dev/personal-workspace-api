def validate_single_line(value: str) -> str:
    if "\n" in value or "\r" in value:
        message = "Important info must be one line"
        raise ValueError(message)
    return value.strip()
