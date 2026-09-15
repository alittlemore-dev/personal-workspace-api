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
- [WireGuard internal access](../docs/wireguard-internal-access.md)
- [Roadmap](../docs/TODO.md)

## Project structure

```text
personal-workspace/
├── src/            # Litestar API and async domain/application code
├── tests/          # Tests and query-plan gates
├── performance/    # Query-plan scenarios and reports
├── infra/          # nginx edge, MinIO wrapper, deployment, TLS and security scripts
├── docs/           # domain, operations, security and roadmap documentation
├── docker-compose.yml
└── .env.example
```

nginx is the TLS edge for the API and private operations endpoints. The shared platform frontend
and integrated runtime are maintained outside this backend repository.

## Quick start

1. Clone the repository and create local configuration:

   ```bash
   cp .env.example .env
   ```

2. Set every value in `.env`. `IMAGE_TAG` is required by Compose; local development may use an
   explicit throwaway tag. Keep actual secrets out of Git.

3. Provide local TLS certificate files under `infra/nginx/certs/` when using the HTTPS edge. The
   nginx container needs read access to them. For production, use the documented Let’s Encrypt flow.

4. Start the stack:

   ```bash
   make run
   ```

## Endpoints

The local nginx edge redirects HTTP to HTTPS.

- API: `https://localhost/api`
- Liveness: `https://localhost/api/healthcheck`
- Readiness: `https://localhost/api/healthcheck/ready`
- API documentation: `https://localhost/api/docs`
- OpenAPI document: `https://localhost/api/docs/openapi.json`

MinIO Console and Databasus are not public. nginx binds them only to `VPN_BIND_ADDRESS` on ports
`18081` and `18082`; see [WireGuard internal access](../docs/wireguard-internal-access.md).

## Quality gates

Use Make targets rather than invoking the underlying tools directly:

```bash
make tests
make security
make query-plans-realistic
```

The query-plan gate exercises current Knowledge and Resume storage queries.
