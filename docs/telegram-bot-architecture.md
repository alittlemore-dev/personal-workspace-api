# Personal Workspace Telegram Bot Architecture

Date: September 26, 2026.

Status: design under review.

## 1. Goal and scope

The Telegram bot lets several people perform a limited set of actions in **one Personal
Workspace**. Family members can add transactions to a shared finance tracker, while each
participant has separate notification preferences. The Workspace owner manages every connection
and its settings in the web application.

One shared bot serves all Workspaces. A connection belongs to the Personal Workspace owner,
rather than to the finance tracker. Finance, tasks, calendar reminders, and saved links are
scenarios attached to the same integration. In the first version, all active connections to one
Workspace have the same available actions. Roles and permissions for individual features are
deferred. **Notification settings are individual to each connection.**

"Shared bot" means one technical Telegram bot identity and one webhook. Each person talks to it
in a separate **private chat**. Messages from different Workspaces or for different people are
never posted to a common chat. The server selects recipient chats from connections and
subscriptions; the bot does not broadcast every event to everyone who has opened it.

The bot creates no web session and grants no access to the web interface, full finance history,
resumes, files, or the entire knowledge database. Competency Trainer is outside this
integration. Group chats, Mini Apps, free-text intent recognition, and voice messages are
outside the first version.

## 2. Current product state and requirements

- `docs/TODO.md` calls for many Telegram users linked to one site user, notifications for
  birthdays, memorable dates, and events, and button-driven quick add for tasks, finance
  transactions, and links in the Recipes, Places, and Watch later categories.
- The calendar already reads memorable dates and people's birthdays from the knowledge database
  for the current and next months. Events, reminders, and the per-person "show/notify about
  birthday" filter are planned.
- The finance tracker, tasks, and the listed link categories are documented but not implemented.
  `docs/finance-tracker-architecture.md` already specifies one owner, multiple Telegram
  participants, transaction creation, and actor auditing. This document defines their shared
  Telegram boundary and replaces the earlier assumption of one bot and token per tracker.
- `auth-api` owns the per-bot enable switch in `UserModel.settings`. `personal-workspace` owns
  invitations, Telegram connections and chat IDs, its bot token, webhook, and commands. The
  Workspace reads the switch through a protected internal `auth-api` endpoint. The Angular page
  reads account settings from `auth-api` and connection data from `personal-workspace`.

## 3. Options considered

| Option | Benefit | Cost | Decision |
| --- | --- | --- | --- |
| One shared bot with Workspace-level connections | One entry point, consistent settings across domains, one webhook | Every operation must enforce owner isolation | Selected |
| One bot per finance tracker | Separate bot identity per tracker | Every owner must supply a token and webhook; poor fit for calendar and tasks | Rejected |
| Permanent link containing the owner's identifier | Easy to reuse | Anyone holding it can repeatedly request access; individual invitations cannot be revoked safely | Rejected |

Invitations use a random, single-use token in a deep link `start` parameter. The link contains
no internal owner identifier, username, or authorization grant.

## 4. Ownership and trust

`UserIdentity.username` from `core.identity` remains the owner boundary. Every Telegram
integration object has an `owner_username`; web reads and writes are always scoped by it. The
numeric Telegram `user.id` identifies a participant. The `@username`, name, and photo are
display snapshots, never authorization identifiers. In the first version, one Telegram `user.id`
can have only one active Workspace connection, so a command sent to the shared bot has one
unambiguous destination. A Workspace can have multiple connections, subject to an explicitly
configured protective limit.

Only the owner with a web session can create invitations, approve pending connections, change
their settings, revoke connections, and block Telegram users. An active Telegram participant may
create records through the supported flows and receive selected notifications. A connection does
not grant permission to edit or delete existing records. This matches the finance architecture's
append-only rule. Initial task and link flows are create-only as well. A participant may leave
the Workspace through the bot, revoking their own connection without affecting anyone else.

Connection states are `pending` (awaiting owner approval), `active`, `revoked`, and `blocked`.
Revocation ends access and lets the owner invite the same person again. Blocking ends access and
prevents that Telegram `user.id` from reconnecting to this Workspace, even with a new valid
invitation. Only the owner can lift the block in web settings. A block in one Workspace does not
affect other Workspaces. State history is retained for auditing; changing connection state never
removes earlier finance transactions or their actor attribution. Revocation or blocking
invalidates open forms, future notifications, and pending approval requests for that Telegram
user.

## 5. Connecting a Telegram account

1. The owner opens Settings → Telegram, enables the integration, and creates an invitation. The
   web interface displays `https://t.me/<shared_bot>?start=<random_token>` and its expiration
   time.
2. A cryptographically secure random generator creates the token. Only its hash is stored. The
   token is single-use and short-lived; the proposed initial lifetime is 15 minutes. The owner
   can cancel an unused invitation. Sharing the link grants the ability to **request** a
   connection, not immediate access. Invitation creation and redemption attempts are
   rate-limited.
3. A person opens the link in a private chat and sends `/start <token>`. The webhook validates
   its secret header, the chat type, token, expiry, integration state, block state, and any
   conflicting active connection. Token consumption and creation of a `pending` request are
   atomic. Redelivery of the Telegram update does not create another request.
4. Web settings show the Telegram ID and the name/username observed at request time. The owner
   approves that specific request to make it `active`, or rejects it. Approval rechecks the
   current state and absence of conflicts.
5. In the first integration phase, the bot acknowledges a pending request. Approval and
   rejection notifications are deferred with the other notification work. Plain `/start`
   without a valid invitation does not create a connection.

A repeated link does not duplicate an active connection. A pending request expires after 24
hours, after which the owner can issue a new invitation. Expired and used tokens receive a
neutral response without exposing owner identity. Pending users cannot use product commands.
Group chats cannot redeem invitations or run product commands.

## 6. Web settings

The integration section has a Workspace-wide enable switch, invitations, and participants. Each
participant row shows an owner-defined label, Telegram ID, username snapshot, connection date,
state, delivery availability, and last successful contact when known. Actions include approving
or rejecting a request, changing its label, switching all or individual notification types,
revoking the connection, blocking the user, and lifting a block. Destructive actions have a
clear confirmation and explain their consequences.

The owner's integration switch stops product commands and notifications for the Workspace but
retains connections and preferences for later reactivation. The **bot's own token** is a
deployment secret and is never entered by the owner in web settings. The UI must distinguish it
from a single-use invitation token.

Each connection stores `notifications_enabled`, switches for stable notification types, an IANA
time zone, and a preferred time for scheduled reminders. All notifications start disabled for a
new connection until the owner explicitly selects them, to avoid unexpectedly sending financial
amounts or personal dates. The connection-wide switch suppresses all types without erasing the
individual selections. If the owner configures which quick-add flows appear, that selection
applies to the Workspace and includes only implemented flows; it does not create hidden
per-participant roles.

### 6.1. Recipient selection

Each notification event has an `owner_username` and a stable type, such as
`finance.transaction_by_other`. The sender loads **only active connections for that owner**. For
each connection it checks the Workspace-wide switch, the connection-wide switch, and the switch
for that event type. It then excludes the actor for an "added by someone else" event and calls
Telegram `sendMessage` separately for each remaining `private_chat_id`. If no connections
remain, no message is sent.

For example, Anna and Boris are linked to the same Workspace. Anna subscribes to birthdays but
disables finance transactions; Boris subscribes to finance transactions but disables birthdays.
Only Anna receives a birthday reminder. Only Boris receives a notification about an expense
added by Anna. The future location of notification preferences will be decided when notification
behavior is implemented; the shared bot token does not affect recipient selection. New
notification types are not enabled automatically
for everyone: the owner selects them for each connection.

## 7. Action and notification catalog

Each source domain owns its business events and actions. The Telegram integration resolves
recipients and delivers messages. The UI displays a scenario only after its domain and delivery
flow work; unfinished roadmap items do not produce empty switches.

| Domain | Bot action | Notification type | Availability |
| --- | --- | --- | --- |
| Finance | Button-guided income/expense → category → amount → currency → date → description → confirmation | `finance.transaction_by_other`: another person added a transaction; `finance.expense_limit_exceeded`: a soft limit was crossed | With finance tracker implementation |
| Calendar and people | No write action initially | `calendar.birthday`; `calendar.memorable_date` | Data is already read by the calendar; scheduling and source filters are needed |
| Calendar events | No write action initially | `calendar.event_reminder` | After one-time and recurring events exist |
| Tasks | "Add task" with short guided input | `tasks.due_reminder` if tasks support due dates and reminders | After task and due-date support exists |
| Links | Recipe, Place, or Watch later button → URL → confirmation | No required notification initially | After those categories exist in the knowledge database or a links domain |

A finance notification about another person's transaction includes the actor, direction, amount,
currency, and category. Its actor does not receive an echo through
`finance.transaction_by_other`. Another actor may be a Telegram participant or the web owner. A
limit notification occurs on a **transition** from within the limit to over it after a confirmed
data change, rather than after every subsequent transaction. Falling below and crossing again
produces a new event. Finance notifications are sent only after the PostgreSQL write commits.

Birthday and date sources need their own filters. The existing roadmap item for
showing/notifying about a particular person's birthday must control event generation before
Telegram recipients are selected. Individual connection preferences then determine who receives
the permitted event. The calendar and bot read the same source data, but delivery does not
depend on whether the browser calendar is open. A recurring date produces one event per year and
type; edits or deletion before delivery cancel a stale reminder.

The catalog may later add notifications about upcoming tasks and new important entries if their
domains provide explicit events and useful recipient context. Changes to resumes, arbitrary
files, and the entire knowledge database are not notification sources in this design.

## 8. Processing and reliability

The shared bot sends webhooks to a separately classified integration HTTP endpoint in
`personal-workspace`. The endpoint validates `X-Telegram-Bot-Api-Secret-Token` **before**
processing payload data and does not rely on a web cookie. The bot sends a private `/start`
settings request to `auth-api` with a separate service credential. `personal-workspace` resolves
the numeric Telegram `user.id` against its own connections. Future product commands must obtain
current connection state from `personal-workspace` before acting; a domain use case never trusts an owner,
category, or object ID from callback data without an owner-scoped check.

Guided forms use buttons and constrained value input, present a summary before final
confirmation, and allow cancellation. Temporary draft state with a TTL lives in Valkey; after it
expires the user starts again. Confirmation rechecks the active connection, integration state,
category ownership, current month, amount, and other domain rules. The confirmed record and the
Telegram update/callback idempotency key are persisted in one PostgreSQL transaction. A repeated
tap, retried webhook, or race between confirmations cannot create another record.

Domains create a durable notification event in the same transaction as the business change,
using a transactional outbox or an equivalent atomic mechanism. After commit, background tasks
resolve subscribed recipients and send messages. A unique delivery record for each (event,
connection, type) prevents duplicate internal scheduling and tracks attempts and outcome. Before
sending, the worker checks the Workspace switch, connection state and preferences, and whether
the source object is still current. Telegram API failures have bounded retries. Permanent errors
and a user blocking the bot appear in web settings without undoing the business change.

A scheduled event key includes its occurrence date, so rerunning the scheduler does not plan
another delivery. Sending to Telegram and marking success in PostgreSQL cannot be one
transaction: a crash between them can occasionally duplicate a message. This limitation should
be disclosed as a delivery property. After a long integration outage, reminders past an explicit
relevance deadline are skipped rather than sent in a backlog burst.

Calendar notification times use the connection's IANA time zone. The finance tracker retains its
own time zone for month boundaries, as defined in the finance architecture. A change of
notification time or time zone affects future deliveries. This gives date-only reminders a clear
meaning for family members in different countries.

## 9. Data and implementation boundaries

Account state in `auth-api` PostgreSQL:

- `UserModel.settings.telegram_bots`: per-bot enabled state, keyed by the `TelegramBotId` enum.

Bot domain state in `personal-workspace` PostgreSQL:

- Telegram invitations: owner username, token hash, expiry, use/cancellation state, and label;
- Telegram connections: owner username, Telegram user ID and private chat ID, state, label,
  profile snapshot, and connection timestamps;
- Product events, update receipts, outgoing delivery records, and possible future connection
  preferences belong here when those features are designed.

The owner username is a cross-service identity and has no database foreign key to an auth table.
The authenticated Workspace API scopes management operations to that username. Database
constraints enforce uniqueness of an active Telegram user ID across Workspaces and single-use
invitation redemption. The bot token and webhook secret come from deployment configuration; raw
invitation tokens are never persisted.

`auth-api` exposes `GET /api/auth/account/me` and `PUT /api/auth/account/me/settings`
for the complete account settings object, including `telegramBots`. The bot reads the switch
through the service-secret-protected internal GET
`/api/auth/internal/telegram/{telegram_bot_id}/settings?ownerUsername=...`, using
`personal-workspace` as its bot ID. The public edge blocks this route.
`personal-workspace` exposes authenticated invitation and connection management and the bot
webhook at `/api/personal-workspace/telegram`. The Angular interface lives in `frontend`.

### 9.1. Telegram library and dependency boundaries

Use **aiogram 3.x** for the Telegram Bot API adapter. The decisive requirement is to test the
bot as an interface layer: feed real Telegram update shapes through its routing, filters, and
dependency injection while replacing domain use cases with test providers. This gives bot tests
the same separation already used for Litestar API, core, and storage tests. aiogram is actively
maintained, supports the service's Python 3.14 runtime, and provides an asynchronous dispatcher,
routers, callback handling, and finite-state-machine support for guided forms. Dishka has a
built-in aiogram integration with a `REQUEST` scope per Telegram event and `FromDishka` injection
into async handlers. [aiogram project](https://pypi.org/project/aiogram/), [Dishka aiogram
integration](https://dishka.readthedocs.io/en/stable/integrations/aiogram.html).

`python-telegram-bot` is also maintained and can process externally supplied updates, but it
has no built-in Dishka integration; this service would need to own the dependency-scope bridge.
`pyTelegramBotAPI` is maintained too, but Dishka's documented integration supports only
synchronous handlers, which does not fit the existing async use cases. These are integration and
testability trade-offs, not claims that either alternative is obsolete. [python-telegram-bot
Application](https://docs.python-telegram-bot.org/telegram.ext.application.html), [Dishka
integrations](https://dishka.readthedocs.io/en/stable/integrations/index.html), [Dishka
pyTelegramBotAPI integration](https://dishka.readthedocs.io/en/stable/integrations/telebot.html).

Litestar owns the HTTP webhook and validates its secret header before parsing or dispatching the
update. After validation it passes the update to aiogram's `Dispatcher.feed_raw_update`; aiogram
routers handle commands, messages, and callbacks. Dishka supplies the owning core use cases to
those handlers. The Litestar HTTP request and the aiogram event are distinct dependency scopes;
the webhook does not pass request-scoped database sessions into bot handlers. TaskIQ remains the
worker and scheduler boundary for outgoing notifications. Its delivery code can use the aiogram
Bot API client without routing an artificial incoming update through the dispatcher. [aiogram
webhook integration](https://docs.aiogram.dev/en/latest/dispatcher/webhook.html).

The bot layer owns Telegram-specific parsing, reply text and buttons, and the steps of guided
input. Temporary form state may use aiogram's FSM with Valkey-backed Redis storage, explicit
TTLs, and appropriate event isolation. It must be possible to clear a participant's form when
access is revoked or blocked. FSM state is never proof of authorization or a durable transaction:
the core use case rechecks the current connection and domain rules on confirmation, and
PostgreSQL enforces idempotency. No additional dialog framework is required for the initial
button-guided flows. [aiogram FSM storage](https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/storages.html).

### 9.2. Test boundaries for the bot

- Bot unit tests construct a dispatcher with the production routers and a test Dishka container
  whose providers return mocked core use cases. They feed representative message and callback
  JSON through `feed_raw_update`, then assert routing, mapped arguments, visible replies,
  buttons, cancellation, and form transitions. Representative cases include `/start` with an
  invitation, pending or revoked access, rejection of group chats, malformed callbacks, and a
  confirmed action reaching the intended use case once. A fake Bot API session captures outgoing
  calls; tests use neither a real token nor the Telegram network. Direct handler tests are useful
  for narrow formatting branches, but dispatcher-level tests prove filters, middleware, and
  injection are wired correctly. [aiogram testing](https://docs.aiogram.dev/en/latest/dispatcher/testing.html).
- A small set of Litestar HTTP tests checks webhook secret rejection before payload processing,
  acceptance of valid updates, and forwarding into the dispatcher. It does not repeat every bot
  conversation through HTTP.
- Core unit tests own invitations, connection and authorization rules, notification eligibility,
  and confirmed actions. Storage and selected integration tests own atomic token consumption,
  unique connections, transaction plus idempotency receipt, outbox, and delivery concurrency.
  Bot tests assert that the appropriate use case is called and its result is presented; they do
  not re-test that use case's business decisions.
- Focused cross-layer tests cover the failure modes that depend on boundaries working together,
  such as a retried webhook, a revoked participant confirming an open form, and a delivery task
  observing changed preferences. These complement, rather than multiply, layer-specific tests.

## 10. Rollout and verification

1. Shared bot and trust model: service configuration, webhook, invitations, approval,
   revocation/blocking, management screen, and Workspace isolation.
2. Individual preferences and reliable delivery: global and per-type switches, outbox, delivery
   states, scheduler, and observability.
3. Calendar notifications for existing birthdays and memorable dates, followed by events after
   their domain exists.
4. Finance quick add and notifications with the finance tracker. The shared Telegram model
   replaces the finance document's former draft bot tables. Tasks and links follow as their
   domains become available.

Critical checks include guessed owner/object IDs, reused and racing invitations, Telegram ID
conflicts between Workspaces, cancellation of pending approval, revocation during a form,
duplicate webhook/callbacks, repeated event delivery, preference changes between event creation
and delivery, time-zone and daylight-saving boundaries, a user blocking the bot, and partial
Telegram API or Valkey failure. Settings changes need API and accessible UI checks. Trust,
money, and delivery need focused integration regressions.

## 11. Questions for later design work

- Should one Telegram `user.id` be able to join multiple Workspaces later? That requires an
  explicit active-Workspace choice in each flow and a revised uniqueness rule.
- Should the owner be able to limit the financial detail shown to individual participants?
  Initially the message format is the same for all subscribed participants.
- What exact delivery times and relevance deadlines should birthdays, dates, and events use?
  This design establishes per-connection time and time zone; product values are selected before
  scheduler implementation.
- Should participants adjust their own notification settings inside the bot? For now the owner's
  web interface remains the source of truth; the bot may only display current settings.

## 12. Verified Telegram constraints

- Telegram supports `https://t.me/<bot>?start=<payload>` deep links. The payload is limited to
  64 characters from the base64url alphabet. [Bot
  Features](https://core.telegram.org/bots/features).
- A bot cannot initiate a private conversation: the participant must open it and send a message
  first. [Bots: An introduction](https://core.telegram.org/bots).
- Webhooks can send a secret in `X-Telegram-Bot-Api-Secret-Token`. Telegram retries unsuccessful
  HTTP deliveries, and `update_id` helps deduplicate them. [Bot
  API](https://core.telegram.org/bots/api).
- `sendMessage` takes a target `chat_id`, allowing the server to address each private chat
  separately. [Bot API](https://core.telegram.org/bots/api#sendmessage).
- Button `callback_data` is limited to 64 bytes, so it holds only a short, non-privileged action
  identifier; state and authorization are checked on the server. [Bot
  API](https://core.telegram.org/bots/api#inlinekeyboardbutton).
