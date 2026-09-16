# Personal Workspace

[🇺🇸 English version](./README.md)

| Категория | Технологии |
| --- | --- |
| Покрытие | ![coverage-backend](./badges/coverage-backend.svg) |
| Backend | ![python](./badges/python.svg) ![litestar](./badges/litestar.svg) ![async](./badges/async.svg) ![pydantic](./badges/pydantic.svg) ![dishka](./badges/dishka.svg) ![taskiq](./badges/taskiq.svg) ![paseto](./badges/paseto.svg) ![argon2](./badges/argon2.svg) |
| База данных | ![postgresql](./badges/postgresql.svg) ![sqlalchemy](./badges/sqlalchemy.svg) ![alembic](./badges/alembic.svg) |
| Кэш | ![valkey](./badges/valkey.svg) |
| Тестирование | ![pytest](./badges/pytest.svg) |
| DevOps | ![docker](./badges/docker.svg) ![nginx](./badges/nginx.svg) ![minio](./badges/minio.svg) ![docker-compose](./badges/docker-compose.svg) |
| Качество | ![ruff](./badges/ruff.svg) ![mypy](./badges/mypy.svg) ![bandit](./badges/bandit.svg) ![pip-audit](./badges/pip-audit.svg) ![trivy](./badges/trivy.svg) ![hadolint](./badges/hadolint.svg) ![dockle](./badges/dockle.svg) ![vulture](./badges/vulture.svg) |

Приватное личное рабочее пространство для резюме и базы знаний. `/login` — единственный
анонимный UI-маршрут; настроенный через окружение аутентифицированный владелец использует
зашифрованную сессию для защищённых доменов `/api/*` (`/api/tools`, `/api/calendar`, `/api/files`,
`/api/resumes`, `/api/knowledge` и `/api/wiki-links`), а доступ к доменным данным остаётся
ограниченным автором для будущей многопользовательской модели.

## Документация

- [База знаний](../docs/knowledge-database.md)
- [Календарь](../docs/calendar.md)
- [План работ](../docs/TODO.md)

## Структура проекта

```text
personal-workspace/
├── src/            # Litestar API и асинхронный доменный/прикладной код
├── tests/          # Тесты и query-plan gates
├── performance/    # Сценарии и отчёты query-plan
├── scripts/        # Backend quality, test и image helpers
├── docs/           # документация доменов, эксплуатации, безопасности и roadmap
├── docker-compose.test.yml
└── Dockerfile
```

Общий frontend и интегрированный runtime поддерживаются соседним
[infra-репозиторием](https://github.com/alittlemore-dev/infra).

## Быстрый запуск

Создайте локальную конфигурацию, установите зависимости, запустите быстрые тесты и соберите образ
сервиса:

```bash
cp .env.example .env
make install
make tests-fast
make build
```

При соседнем расположении checkout один раз выполните `make -C ../infra dev-trust`, затем
запускайте общий стек через `make -C ../infra dev`.

## Endpoints

Общий локальный edge создаётся соседним infra-репозиторием.

- API: `https://alittlemore.localhost/api/personal-workspace/`
- Liveness: `https://alittlemore.localhost/api/personal-workspace/healthcheck`
- Readiness: `https://alittlemore.localhost/api/personal-workspace/healthcheck/ready`
- Документация API: `https://alittlemore.localhost/api/personal-workspace/docs`
- OpenAPI-документ: `https://alittlemore.localhost/api/personal-workspace/docs/openapi.json`

Операционный контракт описан в документации infra-репозитория:
[WireGuard](https://github.com/alittlemore-dev/infra/blob/main/docs/wireguard-internal-access.md)
и [production deployment](https://github.com/alittlemore-dev/infra/blob/main/docs/production-deploy.md).

## Quality gates

Используйте Make targets, а не прямой запуск нижележащих инструментов:

```bash
make tests
make security
make query-plans-realistic
```

Query-plan gate проверяет актуальные storage-запросы Knowledge и Resume.
