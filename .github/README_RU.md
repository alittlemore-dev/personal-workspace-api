# Personal Workspace

[🇺🇸 English version](./README.md)

Приватное рабочее пространство для структурированных резюме, личных знаний, связей, важных дат и
файлов.

## Технологии

| Категория | Технологии |
| --- | --- |
| Покрытие | ![coverage-backend](./badges/coverage-backend.svg) |
| Backend | ![python](./badges/python.svg) ![litestar](./badges/litestar.svg) ![async](./badges/async.svg) ![pydantic](./badges/pydantic.svg) ![dishka](./badges/dishka.svg) ![taskiq](./badges/taskiq.svg) ![paseto](./badges/paseto.svg) ![argon2](./badges/argon2.svg) |
| База данных | ![postgresql](./badges/postgresql.svg) ![sqlalchemy](./badges/sqlalchemy.svg) ![alembic](./badges/alembic.svg) |
| Кэш | ![valkey](./badges/valkey.svg) |
| Тестирование | ![pytest](./badges/pytest.svg) |
| DevOps | ![docker](./badges/docker.svg) ![nginx](./badges/nginx.svg) ![minio](./badges/minio.svg) ![docker-compose](./badges/docker-compose.svg) |
| Качество | ![ruff](./badges/ruff.svg) ![mypy](./badges/mypy.svg) ![bandit](./badges/bandit.svg) ![pip-audit](./badges/pip-audit.svg) ![trivy](./badges/trivy.svg) ![hadolint](./badges/hadolint.svg) ![dockle](./badges/dockle.svg) ![vulture](./badges/vulture.svg) |

## Возможности

- Создание структурированных резюме с разделами профиля, опыта, образования, навыков, языков и
  проектов, а также экспортом в PDF/DOCX
- Личная база знаний с поиском по заметкам, тегами, памятными датами, фотографиями и вложениями
- Каталог людей с настраиваемыми направленными и симметричными связями
- Единый календарь событий базы знаний и дней рождения

## Начало работы

```bash
cp .env.example .env
make install
make run-local
make tests-fast
make build
```
