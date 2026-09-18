# Personal Workspace

[🇷🇺 Russian version](./README_RU.md)

A private workspace for structured resumes, personal knowledge, relationships, important dates,
and files.

## Technologies

| Category | Technologies |
| --- | --- |
| Coverage | ![coverage-backend](./badges/coverage-backend.svg) |
| Backend | ![python](./badges/python.svg) ![litestar](./badges/litestar.svg) ![async](./badges/async.svg) ![pydantic](./badges/pydantic.svg) ![dishka](./badges/dishka.svg) ![taskiq](./badges/taskiq.svg) ![paseto](./badges/paseto.svg) ![argon2](./badges/argon2.svg) |
| Database | ![postgresql](./badges/postgresql.svg) ![sqlalchemy](./badges/sqlalchemy.svg) ![alembic](./badges/alembic.svg) |
| Cache | ![valkey](./badges/valkey.svg) |
| Testing | ![pytest](./badges/pytest.svg) |
| DevOps | ![docker](./badges/docker.svg) ![nginx](./badges/nginx.svg) ![minio](./badges/minio.svg) ![docker-compose](./badges/docker-compose.svg) |
| Quality | ![ruff](./badges/ruff.svg) ![mypy](./badges/mypy.svg) ![bandit](./badges/bandit.svg) ![pip-audit](./badges/pip-audit.svg) ![trivy](./badges/trivy.svg) ![hadolint](./badges/hadolint.svg) ![dockle](./badges/dockle.svg) ![vulture](./badges/vulture.svg) |

## Features

- Structured resume authoring with reusable profile, experience, education, skill, language, and
  project sections, plus PDF/DOCX export
- A personal knowledge database with searchable notes, tags, memorable dates, photos, and
  attachments
- A people directory with custom directional and symmetric relationships
- A calendar that combines knowledge-base events and birthdays into a single view

## Getting started

```bash
cp .env.example .env
make install
make run-local
make tests-fast
make build
```
