import secrets

from core.telegram.schemas import InvitationToken


class InvitationTokenGenerator:
    def generate(self) -> InvitationToken:
        return InvitationToken(secrets.token_urlsafe(32))
