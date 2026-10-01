# Finance Tracker Architecture

Date: October 1, 2026

Status: current-month web tracker, Telegram entry, and finance notifications implemented; historical analytics planned

## 1. Context

The finance tracker brings the behavior of a monthly budget spreadsheet into Personal Workspace
without reproducing a general-purpose spreadsheet engine. It maintains one aggregate balance,
monthly income and expense plans, actual transactions, soft limit visibility, and historical data
that can be recalculated in different currencies.

The web application provides current-month entry, overview, configuration, corrections, and audit
access. Telegram provides confirmed transaction entry and subscribed finance notifications.
Historical analytics remains a later delivery.

The expected data volume is small. The system is therefore designed as a relational module inside
the existing Personal Workspace modular monolith rather than as a separate service or analytical
platform.

## 2. Architectural decisions

- PostgreSQL is the source of truth for all confirmed financial data.
- A tracker has one aggregate balance. Accounts, wallets, and transfers do not exist in the model.
- A calendar month is the budgeting boundary and owns its display currency, opening balance, and
  category plan snapshots.
- Categories have stable identities across months, while their names and planned amounts are
  snapshotted per month.
- A category is permanently either `income` or `expense`.
- Transactions retain their original amount and currency and reference the exact historical
  exchange-rate snapshot used for valuation.
- The initial supported currencies are AMD, RUB, USD, and EUR.
- The first exchange-rate provider is the Bank of Russia. Rates are daily and checked every four
  hours.
- Transaction corrections use current-state rows plus immutable revisions and soft deletion.
- The current month is created lazily and atomically when the web page calls the protected ensure
  operation. Telegram may advance an existing tracker through the same month service.
- One Personal Workspace owner may connect multiple trusted Telegram users to the same tracker.
  Telegram participants have no roles and can only append transactions.
- The shared Personal Workspace bot owns Telegram connections, invites, and notification settings;
  the tracker consumes that trust boundary. See `docs/telegram-bot-architecture.md`.
- Historical analytics remains a PostgreSQL read-model concern until measured scale justifies a
  different store.

The architecture intentionally excludes bank integrations, CSV or Excel imports, multiple
accounts, hard spending limits, user-defined currencies, event sourcing, and ClickHouse.

## 3. System structure

The feature follows the existing `personal-workspace` layer boundaries:

- `core.finance` owns domain schemas, enums, invariants, services, storage/client abstractions,
  exceptions, and concrete use cases. It has no Litestar, SQLAlchemy, Telegram, Valkey, or Bank of
  Russia dependencies.
- `infra.postgresql` owns SQLAlchemy models and implementations of finance storage abstractions.
- `infra.http` owns the Bank of Russia adapter behind a provider-neutral core client interface.
- aiogram `RedisStorage` over Valkey owns temporary Telegram form state only.
- `entrypoints.litestar` exposes the protected finance API and uses the shared Personal Workspace
  Telegram webhook.
- `entrypoints.taskiq` synchronizes exchange rates and delivers committed finance events.
- `infra.ioc` wires adapters and use cases through Dishka.
- The sibling `frontend` repository owns the Angular workspace pages and navigation.

The web API and Telegram adapter call the same finance use cases. Transaction validation,
exchange-rate selection, month creation, and balance calculations are not implemented in transport
layers.

Valkey is not a financial data store. Losing Valkey may discard an unfinished Telegram form but
must not lose or duplicate a confirmed transaction.

## 4. Domain model and invariants

### 4.1. Tracker

A tracker belongs to exactly one Personal Workspace identity and contains all of that owner's
months, categories, and transactions. Telegram connections belong to the Workspace-wide integration.
The tracker has an explicit IANA time zone used for month boundaries and exchange-rate dates.

### 4.2. Month

A month is a calendar month in the tracker's time zone. It contains:

- one display currency;
- one opening balance denominated in that currency;
- category plan snapshots denominated in that currency;
- transactions whose occurrence timestamps fall within the month.

Only the current month is exposed in the initial web interface, but completed months are not made
immutable at the domain or persistence level.

### 4.3. Category

A category has a stable identifier and immutable `income` or `expense` kind. Its monthly snapshot
contains the name, planned amount, display order, and whether it accepts new transactions.

Changing a monthly name or plan does not rewrite earlier snapshots. A stable category identifier
allows cross-month analytics to follow the same category through renames.

Archiving a category stops new transactions and prevents it from being copied into future months.
Existing monthly snapshots and transactions remain intact.

Permanent deletion removes the stable category and all of its monthly snapshots, including
historical snapshots. Existing transactions retain their amount, currency, occurrence time,
income/expense kind, version, deletion state, and revisions. Their category association becomes
absent, and their category name is represented by an empty string. Month totals continue to include
active transactions without a category. Snapshot lineage references are cleared when their source
is removed; subsequent month creation cannot copy the deleted category.

### 4.4. Transaction

A transaction has a positive amount. Its stored direction is selected from the category kind when
the transaction is created or explicitly assigned to another category. The transaction stores:

- original amount and currency;
- actual occurrence timestamp;
- income/expense kind and an optional monthly category association;
- optional description represented as a non-null string;
- creation source and author;
- the exchange-rate set applied to the occurrence date;
- a high-precision RUB reference value;
- optimistic version and soft-deletion state.

The occurrence timestamp must resolve to the transaction's month in the tracker time zone. The
creation timestamp is audit metadata and does not select the exchange rate.

### 4.5. Monthly calculations

All calculations exclude soft-deleted transactions.

```text
actual_income = sum(converted active income transactions)
actual_expense = sum(converted active expense transactions)

closing_balance = opening_balance + actual_income - actual_expense
net_savings = actual_income - actual_expense

expense_difference = planned_expense - actual_expense
income_difference = actual_income - planned_income
```

A negative expense difference indicates a soft-limit overrun. It never rejects a transaction.
Income plans are forecasts; expense plans are soft limits. There are no separate baseline, target,
or hard-limit entities.

## 5. Relational data model

The names below describe logical tables and do not prescribe final SQLAlchemy-generated table
names. Identifiers follow the repository's UUID conventions. Persisted timestamps use the
project-standard UTC-aware type.

```mermaid
erDiagram
    FINANCE_TRACKER ||--o{ FINANCE_MONTH : contains
    FINANCE_TRACKER ||--o{ FINANCE_CATEGORY : owns
    FINANCE_MONTH ||--o{ FINANCE_MONTH_CATEGORY : snapshots
    FINANCE_CATEGORY ||--o{ FINANCE_MONTH_CATEGORY : continues_as
    FINANCE_MONTH_CATEGORY |o--o{ FINANCE_TRANSACTION : classifies
    FINANCE_TRANSACTION ||--o{ FINANCE_TRANSACTION_REVISION : has
    EXCHANGE_RATE_SET ||--|{ EXCHANGE_RATE : contains
    EXCHANGE_RATE_SET ||--o{ FINANCE_TRANSACTION : values
    FINANCE_MONTH ||--o{ MONTH_CURRENCY_CHANGE : records
    EXCHANGE_RATE_SET ||--o{ MONTH_CURRENCY_CHANGE : applies
    WORKSPACE_OWNER ||--o{ TELEGRAM_CONNECTION : trusts
    WORKSPACE_OWNER ||--|| FINANCE_TRACKER : owns
```

### 5.1. `finance_tracker`

- `id`;
- unique `owner_username` corresponding to `core.identity.UserIdentity`;
- required IANA `timezone_name`;
- audit timestamps.

### 5.2. `finance_month`

- `id`, `tracker_id`;
- `period_start`, always the first day of the calendar month;
- `currency`;
- `opening_balance`;
- optional previous-month reference;
- copied closing-balance amount and currency used to initialize the month;
- optimistic `version`;
- audit timestamps.

`(tracker_id, period_start)` is unique.

The copied closing-balance snapshot is not a second balance. It records the transfer basis and
allows the system to detect that an earlier month was later corrected without silently cascading
changes through subsequent months.

### 5.3. `finance_category`

- `id`, `tracker_id`;
- immutable `kind` (`income` or `expense`);
- optional `archived_at`;
- creation timestamp.

### 5.4. `finance_month_category`

- `id`, `month_id`, `category_id`;
- snapshotted `kind`;
- `name` and normalized name;
- `planned_amount` in the month currency;
- `position`;
- `accepting_transactions`;
- optional source month-category reference;
- audit timestamps.

`(month_id, category_id)` is unique. Core rejects duplicate normalized names within one month and
category kind. The snapshotted kind makes historical reads self-contained while core enforces that
it matches the immutable category kind.

### 5.5. `finance_transaction`

- `id`, `month_id`, optional `month_category_id`, required `kind`;
- `original_amount`, `original_currency`;
- `amount_rub`;
- `exchange_rate_set_id`;
- `occurred_at`;
- non-null `description`;
- `source` (`web` or `telegram`);
- immutable `author_id` and `author_label` snapshots (web username or numeric Telegram ID and connection label);
- confirmed form `operation_id` (empty for web transactions);
- optimistic `version`;
- `created_at`, `updated_at`, optional `deleted_at`.

The form identifier has a partial uniqueness constraint for Telegram-created transactions. Different
callback IDs confirming the same form return the saved transaction without another outbox event.
Source and creator survive connection revocation and subsequent web corrections.

The monetary basis changes only when the transaction's amount, original currency, or occurrence
date is explicitly edited. Changing the month display currency never rewrites it.

### 5.6. `finance_transaction_revision`

- `id`, `transaction_id`, sequential revision number;
- action (`update`, `delete`, or `restore`);
- complete previous-state snapshot with a snapshot schema version;
- actor and change timestamp.

The current transaction row is used for normal reads. Revisions are immutable audit snapshots, not
events from which current state must be rebuilt.

### 5.7. `finance_exchange_rate_set`

- `id`;
- provider identifier;
- `effective_on` and `fetched_at`;
- RUB base currency;
- source-payload hash;
- uniqueness across provider, effective date, and payload hash.

### 5.8. `finance_exchange_rate`

- `rate_set_id`, `currency`;
- provider `nominal`;
- normalized `rub_per_unit`;
- uniqueness of currency within a set.

Every set includes RUB with a nominal and value of one. Provider values quoted for multiple units,
such as 100 AMD, are normalized to one unit before persistence.

Rate sets are immutable. If the provider corrects a rate for the same effective date, a new set is
created. Existing transactions remain linked to the set originally applied.

### 5.9. `finance_month_currency_change`

- month reference;
- previous and new currency;
- applied rate-set reference and conversion factor;
- opening-balance and category-plan snapshots before and after conversion;
- actor and change timestamp.

A month currency change converts the opening balance and all category plans in one database
transaction. Original transaction amounts and their rate-set references remain unchanged.

### 5.10. Telegram connections

Invites, connections, per-participant notification preferences, and the shared bot configuration
belong to the Workspace-wide Telegram integration described in
`docs/telegram-bot-architecture.md`. The finance model keeps only transaction source, responsible
actor, and Telegram idempotency metadata; it has no finance-specific bot, token, or membership
tables.

## 6. Money and exchange-rate architecture

Money and exchange-rate calculations use `Decimal` and PostgreSQL `NUMERIC`, never `float`.
Monetary values use `NUMERIC(30, 12)` and normalized rates use `NUMERIC(30, 18)`.

User input accepts two decimal places for RUB, USD, and EUR and whole units for AMD. Intermediate
calculations retain database precision. Presentation uses consistent `ROUND_HALF_UP` rounding to
two places for RUB, USD, and EUR and to a whole unit for AMD.

The Bank of Russia publishes values relative to RUB. The system therefore uses RUB as an internal
reference without making it the tracker or reporting currency.

```text
amount_rub =
    original_amount
    * rub_per_unit(original_currency, operation_rate_set)

amount_in(target_currency) =
    amount_rub
    / rub_per_unit(target_currency, operation_rate_set)

converted_month_value =
    old_value
    * rub_per_unit(old_month_currency, currency_change_rate_set)
    / rub_per_unit(new_month_currency, currency_change_rate_set)
```

Because each transaction references a complete immutable rate set, recalculating it in any of the
supported currencies requires no external provider call.

### 6.1. Rate selection

For an operation date, the rate resolver first reuses a persisted set effective on that exact local
date. Otherwise, the Bank of Russia adapter requests historical data and persists an immutable set
before the financial write begins. On weekends and holidays, the provider may return the preceding
official effective date. A provider request must not hold a month or transaction database lock.

If the provider is unavailable, the latest eligible persisted set may still be used, retaining its
actual effective date. If no eligible set exists, the financial mutation fails without partial
writes.

TaskIQ checks current daily rates every four hours. Identical payloads do not produce duplicate
sets. A future provider adapter may replace or supplement the Bank of Russia adapter, but it may
not rewrite rate sets already referenced by transactions.

Adding another supported currency is a release-time schema and code change. Historical rate sets
required by existing transaction dates must be backfilled and validated before the currency is
enabled.

Official provider references:

- <https://www.cbr.ru/development/SXML/>;
- <https://www.cbr.ru/development/DWS/>;
- <https://www.cbr.ru/eng/currency_base/daily/>.

## 7. Month lifecycle

### 7.1. Initial month

The first web visit sends the selected interface language to an idempotent protected ensure
operation. The tracker copies the account time zone, and the first month starts in RUB for Russian
or USD for English. The initial opening balance is zero. A migration-backed bilingual category
template provides editable names and ordering; all category plans are unset, distinct from an
explicit zero. The template never imports amounts or transactions from the reference spreadsheet.
Changing the interface language later does not change an existing month's currency.

Until the first web initialization completes, Telegram shows an instruction to open Finance on the
website. The bot never initializes a tracker.

### 7.2. Lazy month creation

The current month is created when the web application calls ensure on page entry or a Telegram
participant opens an entry form for an existing tracker. Both use `FinanceMonthService` under the
tracker lock. No midnight scheduler is required.

Creation runs as an idempotent transaction:

1. Resolve the current calendar month in the tracker time zone.
2. Lock month creation for the tracker and period.
3. Copy the previous month's currency.
4. Calculate and copy the previous month's closing balance.
5. Copy active categories, names, ordering, and planned amounts. If several calendar months were
   skipped, create each missing month in order without copying transactions.
6. Persist the transferred closing-balance snapshot.
7. Rely on `(tracker_id, period_start)` uniqueness as the final race guard.

Both web and Telegram use this rollover service; their use cases do not call one another.

### 7.3. Historical corrections

Editing an earlier month does not automatically cascade through later opening balances. When a
recalculated closing balance differs from the snapshot used to initialize the following month, the
system exposes a mismatch.

An explicit synchronization operation replaces the following month's opening balance. If the two
months currently use different currencies, synchronization uses the rate set effective at the time
of synchronization and records the conversion in the audit trail.

## 8. Transaction mutation and audit

The web application may create, update, soft-delete, and restore transactions. Telegram may only
create a transaction after final confirmation.

Transaction creation validates ownership, month boundaries, category kind and availability,
positive amount, currency, input precision, and an eligible exchange-rate set.

Updating amount, original currency, or occurrence date selects a new applicable rate set and
recalculates `amount_rub`. Updating only category or description retains the previous monetary
basis. In both cases, the complete previous state is written to a revision before the current row
is changed.

Updates and deletions require the current optimistic version. A stale request fails with a conflict
rather than overwriting another change. Revision insertion and current-state mutation occur in the
same database transaction.

## 9. Telegram integration

### 9.1. Trust model

The Workspace owner uses the shared Personal Workspace bot, generates one-time invitation links,
confirms pending Telegram connections, and can revoke or block each connection from the web
application. The finance adapter accepts only active connections resolved to that owner. The
connection lifecycle and invitation rules are defined in `docs/telegram-bot-architecture.md`.

All active Telegram members have the same append-only finance capability. There are no participant
roles. The Personal Workspace owner manages trust and bot integration settings through the web app.

The shared webhook is an externally authenticated integration endpoint. It validates its webhook
secret before resolving a connection or processing payload data. The shared bot token, webhook
secret, and raw invitation tokens must never be logged.

### 9.2. Form state machine

The Telegram adapter implements a deterministic step-by-step state machine:

```text
kind -> category -> amount -> currency -> occurred_at -> description -> confirmation
```

The month currency is presented first at the currency step. The occurrence timestamp defaults to
the current time but may be selected within the current month. Description is optional. Final
confirmation is mandatory.

Plain `/start` and `/finance` open a form for an active private-chat participant. `/start <token>`
retains invitation redemption. Categories are filtered by direction and availability and paginated
in groups of eight. Amounts accept a decimal point or comma; AMD requires integers and other
supported currencies allow at most two decimal places. Time is either “Now” or a local
`DD.MM.YYYY HH:MM` value in the tracker zone. Ambiguous or nonexistent local times are rejected.
Every step supports back and cancel.

aiogram `RedisStorage` and Redis event isolation store a separate FSM context for bot, private chat,
participant, owner, and connection, with a 30-minute TTL and absolute form deadline. A form UUID
and step revision reject old buttons. Connection revocation makes its context unusable; an
unconfirmed form expires independently of confirmed records. Changing the month or losing the
selected category invalidates the form.

Confirmation checks access before rate acquisition, then repeats access, owner, month, category,
amount, and time checks after rate acquisition and database locks. The confirmed operation, form
identifier, and finance outbox events share one PostgreSQL transaction. Success is sent after
commit. Temporary failures keep confirmation retryable. A saved confirmation can be recovered by
its form identifier even after the success response or Valkey data is lost.

### 9.3. Financial outbox and subscriptions

`finance.transaction_by_other` is emitted only for a newly created transaction. Web creations go
to all subscribed active connections; Telegram creations exclude the numeric Telegram author.
`finance.expense_limit_exceeded` is emitted after create, update, delete, or restore when rounded
expenses transition from within a plan to above it, independently for the category and month.
An unset plan is not a limit; zero is. The existing month's expense-plan calculation determines
whether a monthly limit exists. Returning within plan rearms the next crossing. Budget and month
currency edits do not emit events. All subscribed participants, including the author, receive limits.

Finance events and deliveries have separate PostgreSQL tables. Deliveries are unique by
`(event, connection, type)` and use locked claims with a lease. Every minute TaskIQ plans and sends
committed events, rechecking source version, deletion state, current limits, connection state,
account integration and notification switches, and the individual subscription. New subscriptions
`notifyFinanceTransaction` and `notifyFinanceLimit` start off; calendar settings remain independent.
Messages follow the connection's RU/EN language. Operation messages show author, direction,
original amount/currency, and category; limit messages show category/month, plan, expenses, and overrun.

Delivery allows three attempts, retries temporary failures after at least 15 minutes, and expires
after 24 hours. Permanent errors end delivery. Terminal history is retained for 90 days. A rare
repeat message remains possible if a worker crashes after Telegram accepts a message but before
PostgreSQL records its outcome; business transactions remain idempotent.

## 10. Entry points and authorization boundaries

Protected web capabilities are mounted under `/api/finance` and use the existing
`request.user.username` and `core.identity` boundary. Storage queries are always scoped by tracker
owner; possession of another entity's identifier is insufficient for access.

`DELETE /api/finance/current-month/categories/{category_id}` archives the current monthly category.
`DELETE /api/finance/current-month/categories/{category_id}/permanent` permanently deletes its
stable category and snapshots and returns the updated current month with HTTP 200. Both operations
require an owned current-month category identifier. Permanent deletion and other tracker writes
share the month-creation transaction lock, so rollover and transaction writes cannot race deletion.
Transaction create/update requests continue to require a valid category; read responses expose
`categoryId: null` and `categoryName: ""` after permanent deletion.

The protected API exposes domain-oriented operations rather than database-shaped CRUD. The first
web delivery implements current-month ensure/read, opening balance and currency changes, category
management, and transaction create/update/soft-delete/restore with revision reads. Telegram entry
uses the shared webhook; historical statistics remain planned. The broader architecture includes:

- tracker initialization and current-month retrieval;
- idempotent current-month creation;
- month summary and transaction reads;
- monthly category and plan management;
- transaction mutation and revision reads;
- month-currency conversion;
- explicit opening-balance synchronization.

The shared Telegram webhook does not use a web user session. It resolves the tracker only after
validating the webhook secret and an active connection belonging to the Workspace owner, then
invokes the same finance use cases used by the protected API.

The Angular frontend treats backend calculations as authoritative. It does not maintain a separate
balance or currency-conversion implementation.

## 11. Consistency and concurrency

The following operations are atomic database transactions:

- lazy month creation with its opening balance and category snapshots;
- transaction creation with its notification event and Telegram idempotency metadata when applicable;
- transaction mutation with its previous-state revision;
- month-currency conversion with opening-balance and plan updates;
- explicit opening-balance synchronization.

Month creation uses locking plus a unique database constraint. Transaction updates use optimistic
versions. Rate-set rows are immutable. These mechanisms prevent duplicate months, duplicate
Telegram transactions, lost transaction updates, and historical rate drift.

Closing balances and category actuals are derived from active transaction rows. They are not stored
as independent mutable aggregates. At the expected data volume, indexed PostgreSQL aggregation is
sufficient. The primary read indexes cover tracker/month, occurrence time, monthly category,
deletion state, and Telegram idempotency identifiers.

## 12. Failure handling

- A missing initial month prevents Telegram writes and requires tracker initialization through the
  protected web flow.
- A missing exchange rate with no available provider response aborts the financial mutation without
  partial data.
- A rate from an earlier business day is valid for weekends and holidays; its actual effective date
  remains visible in transaction details.
- If a category is archived while a Telegram form is open, final confirmation fails and the draft
  cannot create a transaction against it.
- If the calendar month changes while a Telegram form is open, the draft is invalidated rather than
  silently moved to the new month.
- A repeated Telegram webhook or callback does not create a second transaction.
- A stale web update produces a conflict rather than last-write-wins behavior.
- A rate synchronization failure is observable and retryable. Existing persisted rates continue to
  support reads and eligible writes.
- Losing Valkey expires drafts only; PostgreSQL-backed finance data remains intact.

## 13. Security and privacy

- Web access is scoped by `owner_username` in storage queries.
- Finance web routes are protected product routes.
- The shared Telegram webhook is authenticated with its secret before payload processing.
- The bot token is a deployment secret owned by the Workspace-wide integration.
- Invitation tokens are cryptographically random, single-use, expiring, and stored only as hashes.
- Telegram numeric user IDs are identities; display names are untrusted labels.
- Revocation is checked again at final confirmation and invalidates any existing draft.
- Financial descriptions, full Telegram payloads, monetary values, and integration secrets are not
  emitted as raw log fields.
- Transaction creation and every subsequent revision retain their responsible actor.

## 14. Analytics extension

Historical analytics is a read-model extension over the same PostgreSQL data. A future
`reporting_currency` parameter changes presentation only and does not mutate month currencies.
Each transaction is converted through its own historical rate set.

Cross-month category analytics groups by stable `category_id`, so renames do not fragment the
series. Historical month-category snapshots retain the label and plan that were valid in each
period.

Sliding day, week, month, and year views aggregate actual transactions. Monthly plans apply to
calendar months and are not proportionally projected into arbitrary sliding windows.

Materialized aggregates or ClickHouse should be introduced only after measured query latency or
data volume demonstrates that indexed PostgreSQL aggregation is insufficient.
