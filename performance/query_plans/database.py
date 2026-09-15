from __future__ import annotations

import argparse
import re
from hashlib import sha256
from sys import stdout

from sqlalchemy import URL, create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.pool import NullPool

from infra.config.settings import settings
from scripts.pytest_parallel import quote_postgresql_identifier

_POSTGRESQL_IDENTIFIER_MAX_BYTES = 63
_OWNED_DATABASE_PATTERN = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*_test_query_plans_[0-9a-f]{12}$",
)


def build_run_database_name(*, base_name: str, run_id: str) -> str:
    quote_postgresql_identifier(base_name)
    if not base_name.endswith("_test"):
        msg = f"query-plan database base must end in '_test', got {base_name!r}"
        raise ValueError(msg)
    normalized_run_id = run_id.strip()
    if not normalized_run_id:
        msg = "query-plan run id must not be blank"
        raise ValueError(msg)
    run_hash = sha256(normalized_run_id.encode()).hexdigest()[:12]
    suffix = f"_test_query_plans_{run_hash}"
    prefix_limit = _POSTGRESQL_IDENTIFIER_MAX_BYTES - len(suffix.encode())
    truncated_base = base_name.removesuffix("_test").encode()[:prefix_limit].decode("ascii")
    database_name = f"{truncated_base}{suffix}"
    validate_owned_database_name(database_name=database_name)
    return database_name


def validate_owned_database_name(*, database_name: str) -> None:
    if (
        len(database_name.encode()) > _POSTGRESQL_IDENTIFIER_MAX_BYTES
        or _OWNED_DATABASE_PATTERN.fullmatch(database_name) is None
    ):
        msg = f"refusing to manage non-owned query-plan database: {database_name!r}"
        raise ValueError(msg)


def maintenance_database_url() -> URL:
    return URL.create(
        drivername=settings.database.driver,
        username=settings.database.user,
        password=settings.database.password.get_secret_value(),
        host=settings.database.host,
        port=int(settings.database.port),
        database="postgres",
    )


def create_database(*, engine: Engine, database_name: str) -> None:
    validate_owned_database_name(database_name=database_name)
    with engine.connect() as connection:
        connection.execute(text(f"CREATE DATABASE {quote_postgresql_identifier(database_name)}"))


def drop_database(*, engine: Engine, database_name: str) -> None:
    validate_owned_database_name(database_name=database_name)
    with engine.connect() as connection:
        terminate_database_connections(connection=connection, database_name=database_name)
        connection.execute(
            text(f"DROP DATABASE IF EXISTS {quote_postgresql_identifier(database_name)}"),
        )


def terminate_database_connections(*, connection: Connection, database_name: str) -> None:
    connection.execute(
        text(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = :database_name AND pid <> pg_backend_pid()",
        ),
        {"database_name": database_name},
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage an isolated query-plan database.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    name_parser = subparsers.add_parser("name")
    name_parser.add_argument("--base-name", required=True)
    name_parser.add_argument("--run-id", required=True)
    for command in ("create", "drop"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--database-name", required=True)
    args = parser.parse_args()
    if args.command == "name":
        database_name = build_run_database_name(base_name=args.base_name, run_id=args.run_id)
        stdout.write(f"{database_name}\n")
        return
    engine = create_engine(
        maintenance_database_url(),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    try:
        if args.command == "create":
            create_database(engine=engine, database_name=args.database_name)
        else:
            drop_database(engine=engine, database_name=args.database_name)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
