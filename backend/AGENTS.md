# Backend Instructions

These rules apply to all backend-owned code, configuration, tooling, documentation, and supporting
files under `backend/`. Keep shared cross-project configuration and common infrastructure outside
`backend/`.

## Code Style

- Use `backend/pyproject.toml` as the source for formatting, lint, and typing configuration.
- No docstrings unless interface is non-obvious from types
- Comments: only for non-obvious WHY, never WHAT
- No Python class name may start with a leading underscore anywhere under `backend/`, including
  production code, tests, migrations, scripts, and performance tooling; there are no exceptions.
  Give every class a clear public name and control module exports through import/export boundaries
  rather than private class naming.
- Keep environment/configuration values, shared operational limits, and configurable policy values
  in `backend/src/infra/config/constants.py`. Domain invariants, parser-specific rules, adapter-local
  mappings, and other implementation constants belong with the domain, parser, or adapter that owns
  them. Core code must receive infrastructure-owned configuration through schemas, constructor
  parameters, or IOC wiring, while infra and entrypoint code may import `constants` directly when
  that layer owns the wiring.

## Layers

| Layer | Path | Responsibility |
|---|---|---|
| Domain | `backend/src/core/` | Business logic. Pure Python only. |
| Persistence | `backend/src/infra/postgresql/` | SQLAlchemy models + concrete storage implementations |
| Interface | `backend/src/entrypoints/litestar/` | HTTP handlers and API endpoints |
| DI | `backend/src/infra/ioc/` | Dishka providers. Wiring only, no logic |
| Config | `backend/src/infra/config/` | Pydantic settings, logging setup |
| File storage | `backend/src/infra/s3/` | S3-compatible files adapter for MinIO |

## Tooling Boundaries

- Performance and test tooling may import reusable application contracts from `backend/src`, such
  as enums, schemas, factories, and public helpers, but tooling-specific infrastructure must live
  with that tooling. Do not create performance-only or test-only support modules under
  `backend/src`; keep performance support under `backend/performance/` and test support under
  `backend/tests/`.

## Operation Boundaries

- Do not model entity mutation methods as `upsert` when the behavior can create, update,
  delete, or otherwise mutate different state. Use explicit operation-specific names and methods
  such as `create_*`, `update_*`, `delete_*`, `publish_*`, or `set_*` so callers cannot
  accidentally trigger broader behavior than intended.

## Business Logic Boundaries

- Business-operation orchestration and flows that coordinate multiple storages belong in domain use
  cases under `backend/src/core/**/use_cases.py`. Invariants and behavior owned by one entity or
  value object belong on that domain object. Shared cross-use-case domain behavior belongs in an
  explicit core domain service.
- When an existing use-case operation already represents the business action, reuse it with
  explicit parameters that model transport/quota differences instead of adding a parallel
  use-case method for the same action. Do not use sentinel values such as arbitrarily large quotas;
  make the variation explicit in the parameter contract.
- API controllers, Litestar handlers, API schemas, Dishka providers, storages, ORM models, settings,
  event dispatchers, and infrastructure adapters must not own business decisions. They may validate
  transport shape, map data, wire dependencies, persist/load data, or call a use case.
- Request-level access checks and input checks that can be decided before entering a use case should
  live at the Litestar boundary, preferably as guards or `Provide` dependencies. Do not hide those
  checks in controller helper functions.
- Do not add private module-level helper functions in backend source to hold business behavior.
  Put the behavior on the real owning class or use case instead.
- Do not create classes that exist only to wrap one or more `@classmethod` helpers. A class must
  represent a real domain concept, interface, adapter, provider, guard, schema, model, or service.
- Put reusable domain parsers in the domain `parsers.py`, reader interfaces in `readers.py`,
  parser/request DTOs and rule objects in `schemas.py`, and parser/domain errors in
  `exceptions.py`. Do not name domain files after one narrow feature when an existing standard
  file type fits the object.
- Top-level functions are acceptable when the framework or tool naturally requires them or when a
  callable class would add ceremony without improving ownership: app factories, Litestar lifespan
  hooks, CLI commands, Alembic migration functions, and small pure infrastructure entrypoints.
- When choosing between a function and a method, prefer the shape that expresses real ownership.
  Do not move code into a class solely to satisfy a stylistic ban on functions.
- Prefer moving meaningful multi-parameter object creation into methods on the object that owns
  that creation logic, or into the owning use case when the object is an aggregate/read model.
  Do not extract creation solely for tiny objects with too few fields to justify the extra method.
- Storage adapters may filter, group, paginate, count, and otherwise aggregate data when those
  operations are part of the database query shape. They should return persisted entities or narrow
  row/query results. Product-facing composition, cross-storage assembly, and business decisions must
  remain in core use cases or on the owning core object. Simple collection containers may remain at
  storage boundaries when they only wrap loaded values.

## HTTP and Schemas

- Controllers must receive dependencies through `FromDishka[...]`, typed as the concrete use case
  class registered in Dishka.
- Endpoint/controller modules must not define `@staticmethod`, `@classmethod`, or private helper
  methods for request-derived values or parameter assembly when a Litestar `Provide` dependency can
  own that logic. Put those dependencies in a neighboring `dependencies.py` module.
- Assemble query/path/header/cookie parameter objects in neighboring `dependencies.py` Litestar
  `Provide` dependencies when this keeps handlers focused on their HTTP contract.
- API schemas must inherit from the shared schema bases and map explicitly between API, ORM, and
  core representations. Use `to_domain_schema` for conversion to the same core concept and
  `from_domain_schema` for conversion from it when the method signature identifies the exact
  source/target type. Use a specific semantic conversion name only when the conversion changes the
  concept.
- Do not use `cast("Self", ...)` to suppress classmethod return-type errors. Use an accurately typed
  constructor or an explicit concrete return type.
- Do not pass Pydantic API schemas, SQLAlchemy models, or Litestar types into the core layer.

## Response Caching

- Cache API GET responses only through the domain response cache helpers in
  `backend/src/entrypoints/litestar/response_cache.py`. Use a `ResponseCacheDomain`
  and its `cache_key_builder` property so keys are domain-prefixed and routed to the
  matching Valkey namespace; do not add ad hoc cache key builders or write directly to a
  shared response-cache namespace.
- Safe, stable GET handlers may use Litestar response caching with explicit cache metadata.
  Keep request-scoped statistics, analytics, file-management, and other request-side-effect or
  user-specific responses uncached unless a new design explicitly
  makes their cache key and invalidation rules safe.
- If a cached GET depends on permission-sensitive query parameters, enforce the access check with a
  Litestar guard or another pre-cache boundary check. Do not rely only on controller body checks
  because Litestar can return a cached response before executing the handler body.
- Mutating handlers that change cached domain content must call
  `invalidate_response_cache_domain_for_mutation(...)` only after the use case succeeds. The helper
  must not invalidate before commit; it registers one post-commit action that first invalidates the
  domain and then enqueues its TaskIQ warm. The action must run only after a successful database
  commit, never after rollback or a failed commit. Do not invalidate or enqueue on
  validation/permission/use-case failures, and do not invalidate content caches for analytics-only
  changes when analytics are served from separate uncached endpoints.
- Response-cache warmers live under `backend/src/entrypoints/taskiq/cache_warm/` and must write
  Litestar-compatible msgpack-encoded ASGI response messages through `ResponseCacheDomainStore`.
  Do not write raw JSON response-cache payloads.

## Background Tasks

- TaskIQ entrypoints live under `backend/src/entrypoints/taskiq/`.
- Keep `backend/src/entrypoints/taskiq/broker.py` as the shared broker and
  `backend/src/entrypoints/taskiq/worker.py` as the worker/scheduler registry entrypoint.
- Put domain task wrappers in domain packages such as
  `backend/src/entrypoints/taskiq/cache_warm/tasks.py`; do not collect unrelated tasks in a
  top-level `tasks.py`.
- Background tasks are internal worker/scheduler processes, not HTTP handlers.
- Run exactly one TaskIQ scheduler process in deployment. Scale TaskIQ workers when more background
  execution capacity is needed.
- TaskIQ result metadata is operational and ephemeral in Valkey unless a future durable task
  history/auditing design explicitly chooses another backend.

## I18n

- The backend i18n catalog is the source of truth for UI interface strings and enum labels.
  Database/content localisation is separate from the UI catalog.
- Resumes are single-language structured documents: store required `LanguageEnum`/`language` on the
  resume, keep one content shape without resume-specific `*_ru` / `*_en` fields, and do not validate
  whether the authored text actually matches the selected language.
  Do not add generic translation tables, production defaults, or fallback language behavior unless
  an explicit design change asks for them.
- Localized read-facing core entities and read models should carry language-neutral projected fields
  such as `title`, `content`, and `name`, selected for the requested
  `LanguageEnum` before those objects are constructed. Write and persistence contracts may retain
  explicit RU/EN fields when both translations are required. Do not require canonical RU/EN fields
  on every read-facing core entity.
- Supported UI languages must be modeled with a backend enum. Do not accept arbitrary language
  strings in production API/settings code.
- The default UI language must be configured explicitly through the required
  `I18N_DEFAULT_LANGUAGE` environment setting; do not add production defaults for it.
- Keep the available-languages endpoint and bundle endpoint consistent with the enum and catalog,
  and cover new languages/keys with catalog parity tests.
- The available-languages and bundle endpoints are deliberately anonymous; keep them aligned with
  the configured language enum and do not attach private workspace data to their responses.
- Health endpoints remain explicitly anonymous operational support endpoints. Keep their responses
  minimal and do not reuse them for user or workspace state.
- Content localisation beyond resumes remains future work until explicitly designed.

## Persistence

- SQLAlchemy models and database storages live only under `backend/src/infra/postgresql/`.
- Database storages return domain schemas, not ORM models.
- Storages may `flush`, but must not `commit`; transaction ownership belongs to the DI/session provider.
- Every DB model change must include a matching Alembic migration.

## Knowledge Database

- Model common knowledge metadata through the generic typed item contract and add normalized
  one-to-one extension tables plus type-specific use-case facades. Do not add JSON/EAV attribute
  bags, generic persisted field definitions, or storage methods named for one item type when the
  operation is truly common.
- Keep Knowledge implementations partitioned into matching `items`, `files`, and `people`
  subpackages across core, Litestar API, PostgreSQL models/storages, and IOC providers. Keep the
  Knowledge API root limited to router composition instead of rebuilding a cross-feature monolith.
  Domain enums belong to the subpackage that owns their meaning; do not collect item-, file-, and
  people-specific enums in a shared Knowledge root module.
- Every knowledge list, lookup, join, mutation, taxonomy operation, relationship operation, and
  file operation must include `author_username` in its database predicate.
  Preserve composite author foreign keys and cover guessed-ID/cross-author behavior with storage,
  use-case, and API IDOR tests.
- Keep People free-text search limited to first, middle, and last names plus email. Phone and
  Telegram are stored contact fields and must not become search predicates or indexed search
  targets without an explicit product-design change.
- Private knowledge objects use the internal-only `knowledge-private` client and protected backend
  streaming. Never return a public/presigned object URL, add anonymous bucket policy/CORS, or remove
  S3 objects before transaction commit. Keep replacement/deletion cleanup post-commit and
  best-effort. After a new private object upload succeeds, register it for request rollback and
  commit-failure cleanup; never run that cleanup after a successful commit. Keep raw query values,
  concrete private knowledge paths/path parameters, and private object details out of
  request/cleanup logs.

## Dependency Injection

- Dishka providers are wiring only: no business logic, DB queries, or external side effects.
- Use `Scope.APP` only for stateless singleton-safe dependencies; use `Scope.REQUEST` for sessions, storages, and use cases.
