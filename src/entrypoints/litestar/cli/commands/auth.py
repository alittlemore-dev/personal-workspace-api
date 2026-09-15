import click
from argon2 import PasswordHasher as Argon2CryptContext

from core.schemas import Secret
from infra.auth.password_hashers import Argon2PasswordHasher


@click.command()
def hashpassword_command() -> None:
    password: str = click.prompt(
        "Password",
        hide_input=True,
        confirmation_prompt=True,
        type=str,
    )
    password_hash = Argon2PasswordHasher(context=Argon2CryptContext()).hash(
        password=Secret(password),
    )
    click.echo(password_hash)
