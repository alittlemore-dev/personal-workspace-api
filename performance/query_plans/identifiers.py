from hashlib import md5


def seeded_identifier(*, prefix: str, value: int) -> str:
    return md5(f"{prefix}-{value}".encode(), usedforsecurity=False).hexdigest()
