# Personal Workspace

[🇷🇺 Russian version](./README_RU.md)

| Category | Technologies |
| --- | --- |
| Coverage | ![coverage-backend](./badges/coverage-backend.svg) |
| Backend | ![python](./badges/python.svg) ![litestar](./badges/litestar.svg) ![async](./badges/async.svg) ![pydantic](./badges/pydantic.svg) ![dishka](./badges/dishka.svg) ![taskiq](./badges/taskiq.svg) ![paseto](./badges/paseto.svg) ![argon2](./badges/argon2.svg) |
| Database | ![postgresql](./badges/postgresql.svg) ![sqlalchemy](./badges/sqlalchemy.svg) ![alembic](./badges/alembic.svg) |
| Cache | ![valkey](./badges/valkey.svg) |
| Testing | ![pytest](./badges/pytest.svg) |
| DevOps | ![docker](./badges/docker.svg) ![nginx](./badges/nginx.svg) ![minio](./badges/minio.svg) ![docker-compose](./badges/docker-compose.svg) |
| Quality | ![ruff](./badges/ruff.svg) ![mypy](./badges/mypy.svg) ![bandit](./badges/bandit.svg) ![pip-audit](./badges/pip-audit.svg) ![trivy](./badges/trivy.svg) ![hadolint](./badges/hadolint.svg) ![dockle](./badges/dockle.svg) ![vulture](./badges/vulture.svg) |

Private personal workspace for resumes and the Knowledge database. `/login` is the only anonymous
UI route; the environment-configured authenticated owner uses an encrypted session for the protected
`/api/*` product domains (`/api/tools`, `/api/calendar`, `/api/files`, `/api/resumes`,
`/api/knowledge`, and `/api/wiki-links`), and domain access remains author-scoped for a future
multi-user model.

## Documentation

- [Knowledge database](../docs/knowledge-database.md)
- [Calendar](../docs/calendar.md)
- [Roadmap](../docs/TODO.md)

## Project structure

```text
personal-workspace/
├── src/            # Litestar API and async domain/application code
├── tests/          # Tests and query-plan gates
├── performance/    # Query-plan scenarios and reports
├── scripts/        # Backend quality, test, and image helpers
├── docs/           # domain, operations, security and roadmap documentation
├── docker-compose.test.yml
└── Dockerfile
```

The shared platform frontend and integrated runtime are maintained by the sibling
[infra repository](https://github.com/alittlemore-dev/infra).

## Quick start

Create local configuration, install dependencies, run the fast test gate, and build the service
image:

```bash
cp .env.example .env
make install
make tests-fast
make build
```

With sibling checkouts, start the integrated stack via `make -C ../infra dev-trust` once and then
`make -C ../infra dev`.

## Endpoints

The shared local edge is created by the sibling infra repository.

- API: `https://alittlemore.localhost/api/personal-workspace/`
- Liveness: `https://alittlemore.localhost/api/personal-workspace/healthcheck`
- Readiness: `https://alittlemore.localhost/api/personal-workspace/healthcheck/ready`
- API documentation: `https://alittlemore.localhost/api/personal-workspace/docs`
- OpenAPI document: `https://alittlemore.localhost/api/personal-workspace/docs/openapi.json`

See the infra repository's
[WireGuard guide](https://github.com/alittlemore-dev/infra/blob/main/docs/wireguard-internal-access.md)
and [production deployment guide](https://github.com/alittlemore-dev/infra/blob/main/docs/production-deploy.md)
for the operational contract.

## Quality gates

Use Make targets rather than invoking the underlying tools directly:

```bash
make tests
make security
make query-plans-realistic
```

The query-plan gate exercises current Knowledge and Resume storage queries.
