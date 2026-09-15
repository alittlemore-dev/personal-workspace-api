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
- [Внутренний доступ WireGuard](../docs/wireguard-internal-access.md)
- [План работ](../docs/TODO.md)

## Структура проекта

```text
personal-workspace/
├── src/            # Litestar API и асинхронный доменный/прикладной код
├── tests/          # Тесты и query-plan gates
├── performance/    # Сценарии и отчёты query-plan
├── infra/          # nginx edge, обёртка MinIO, deploy, TLS и security-скрипты
├── docs/           # документация доменов, эксплуатации, безопасности и roadmap
├── docker-compose.yml
└── .env.example
```

nginx — TLS edge для API и внутренних операционных endpoints. Общий frontend и интегрированный
runtime поддерживаются вне этого backend-репозитория.

## Быстрый запуск

1. Склонировать репозиторий и создать локальную конфигурацию:

   ```bash
   cp .env.example .env
   ```

2. Заполнить все значения в `.env`. Compose требует `IMAGE_TAG`; для локальной среды укажите
   явный временный tag. Реальные secrets не коммитить.

3. При запуске через HTTPS edge положить локальные TLS-файлы в `infra/nginx/certs/`. Контейнер
   nginx должен иметь к ним read-доступ. Для production используйте описанный Let’s Encrypt flow.

4. Запустить стек:

   ```bash
   make run
   ```

## Endpoints

Локальный nginx edge перенаправляет HTTP на HTTPS.

- API: `https://localhost/api`
- Liveness: `https://localhost/api/healthcheck`
- Readiness: `https://localhost/api/healthcheck/ready`
- Документация API: `https://localhost/api/docs`
- OpenAPI-документ: `https://localhost/api/docs/openapi.json`

MinIO Console и Databasus не публичны. nginx привязывает их только к `VPN_BIND_ADDRESS` на портах
`18081` и `18082`; см. [Внутренний доступ WireGuard](../docs/wireguard-internal-access.md).

## Quality gates

Используйте Make targets, а не прямой запуск нижележащих инструментов:

```bash
make tests
make security
make query-plans-realistic
```

Query-plan gate проверяет актуальные storage-запросы Knowledge и Resume.
