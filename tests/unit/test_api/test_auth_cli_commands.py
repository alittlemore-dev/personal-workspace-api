from click.testing import CliRunner

from entrypoints.litestar.cli.commands.auth import hashpassword_command
from tests.helpers.factories.core import TEST_OWNER_PASSWORD


def test_hashpassword_command_confirms_password_and_prints_only_argon2id_hash() -> None:
    result = CliRunner().invoke(
        hashpassword_command,
        input=f"{TEST_OWNER_PASSWORD}\n{TEST_OWNER_PASSWORD}\n",
    )

    assert result.exit_code == 0
    assert "Repeat for confirmation" in result.output
    assert TEST_OWNER_PASSWORD not in result.output
    assert result.output.rstrip().splitlines()[-1].startswith("$argon2id$")
