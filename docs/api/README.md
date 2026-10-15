# HTTP API and integrations

[Documentation](../README.md) · [Project home](../../README.md)

The machine-readable contract is [openapi.yaml](openapi.yaml), using OpenAPI 3.1.1. Import it into an OpenAPI-compatible viewer or HTTP client to inspect operations, request bodies, response schemas and authentication. The file describes the current source tree, including coaching and legacy push subscriptions; it is not a separately versioned service. It is checked by the Python test suite. The application does not currently serve a Swagger UI.

## Authentication

Send `Authorization: Bearer TOKEN` on every `/api/*` request except `/api/config`, `/api/auth/register` and `/api/auth/login`. `/healthz` is also public. Registration and login return an opaque session token with a fixed lifetime: 24 hours for `client: "web"` (the default), or 30 days for `client: "android"`. Activity does not renew the expiry. The client field is a declared preference, not device attestation. Previously issued tokens keep their existing expiry because legacy sessions do not record their client type. Older Android versions that omit `client` receive a 24-hour session on their next login. Usernames are case-insensitive, with 3–40 ASCII letters, digits, `_`, `.` or `-`; registration passwords require 12–256 characters. Tokens created through `/api/tokens` last 365 days and grant full account access. Copy them when created; they cannot be retrieved later.

All data is scoped to the authenticated account. Revoking the current token or logging out invalidates it. JSON request bodies are limited to 16 KiB. Errors usually contain `error` (a localized message) and `code` (a stable identifier). Messages use the account language, or `Accept-Language` before authentication, falling back to English. SSE capacity errors contain only `error`.

## Settings, entries and statistics

Settings updates are partial. For example, `{"language":"en"}` changes only the language; `{"pack_price":"600","currency":"JPY","pack_size":20,"daily_target":10,"timezone":"Asia/Tokyo"}` updates pricing and daily preferences. A currency change requires `pack_price`. Prefer a decimal string for prices; the maximum is 1,000,000 currency units and precision must match the currency. The legacy `pack_price_cents` field always means hundredths and cannot represent all three-decimal currencies. The daily target does not prevent additional entries.

`/api/config` exposes supported languages, currencies and time-zone choices. `timezone_options` contains geographic labels, search text and current UTC offsets; `timezone_aliases` maps aliases to catalog representatives. Existing valid time zones outside the simplified catalog remain accepted. `/api/settings` includes `timezone_info`, server-calculated `local_today` and `local_datetime`, reminder preferences and the current coaching goal.

`POST /api/cigarettes` accepts optional `quantity` (1–200, default 1), `source` (`web`, `android`, `api`, `streamdeck`), `trigger` and a timestamp. The source is descriptive, not proof of origin. Omit the body to record one cigarette now. `occurred_at` requires a UTC offset; `occurred_at_local` has no offset and is interpreted in the account time zone. They are mutually exclusive. Dates before 2000 or in the future are rejected. An explicit offset timestamp at most five seconds ahead is clamped to receipt time to tolerate device clock skew. Manual local timestamps remain strict. Nonexistent DST times are rejected; repeated local times use the first occurrence.

An optional `Idempotency-Key` (1–100 ASCII letters, digits, `_`, `.`, `:`, `-`) belongs to the account and entry. Reusing it returns the first entry, even with a changed body: initial response `201`, replay `200`. Deleting that entry releases its key. Without a key each request creates another entry.

`/api/cigarettes`, `/api/stats` and `/api/export.csv` accept inclusive `start` and `end` dates in the account time zone. The default is 30 days ending today; the maximum is 366 days, with no dates before 2000 or after today. History also supports `limit` (1–500, default 100) and `offset` (0–10,000,000, default 0), returning `items` and `total`.

Statistics include today, all-time totals, the selected period and daily totals. Today and all-time totals are independent of the filter. `analysis` adds period averages, previous-period comparisons, daily deviations, a moving average over at most seven days, 24 hourly buckets, seven weekday buckets (Monday = 0), and a 30-day projection based on completed days. Percentages with a zero reference are `null`; unavailable previous periods have null boundaries and quantity deltas. Projections without completed days have null quantity and empty costs.

Costs retain the price and currency at entry time, in millionths of a currency unit. Totals are accumulated by currency before rounding, so rounded individual costs may not sum exactly to the rounded total. `costs` is a currency-to-number map. Legacy scalar `cost` and `currency` are null for mixed currencies. Empty totals contain zero in the account currency. The CSV has a UTF-8 BOM and stable columns `id,local_datetime,quantity,cost,currency,source`.

## iPhone Shortcuts

The [SuuLess +1 guide](../user-guide/iphone-shortcut.md) shows how to configure an authenticated JSON request in Apple Shortcuts and add it to the Home Screen. It uses `POST /api/cigarettes` with `{"quantity":1,"source":"api"}` and a personal API key; no additional endpoint or native iOS app is required.

## Stream Deck

Create a token in **Settings & integrations → API keys & sessions**, then configure an HTTP action:

| Field | Value |
|---|---|
| Method | `POST` |
| URL | `https://YOUR_SERVER/api/cigarettes` |
| Authorization | `Bearer YOUR_TOKEN` |
| Content-Type | `application/json` |
| Body | `{"source":"streamdeck"}` |

```sh
# Supply STOP_CLOP_TOKEN through your shell environment.
curl --fail-with-body https://YOUR_SERVER/api/cigarettes \
  -H "Authorization: Bearer $STOP_CLOP_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"source":"streamdeck"}'
```

If the action retries requests, generate one unique `Idempotency-Key` per button press and reuse it only for that press's retries. A constant key would prevent subsequent presses from being counted. Keep the token out of URLs. No repository-specific Stream Deck plugin is required; use an action that supports HTTP requests.

## Synchronization and coaching

The [synchronization guide](../development/synchronization.md) explains SSE events, cursors and reconnection. `/api/push` retains optional legacy relay subscription operations; normal clients use `/api/sync/events` directly.

The [coaching guide](../user-guide/coaching.md) explains plans, baselines, confirmations, cravings and calculations. Plan changes require the current `version`; conflicts return `409`. A baseline can be fixed only once, over 1–90 completed days with a nonzero total. Daily confirmations check the expected quantity and return `409` if it changed. Future confirmation dates are rejected.

Craving creation requires an idempotency key and accepts a trigger, a strategy (`walk`, `water`, `breathe`, `distract`) and 1–15 minutes (default 3). A replay or an already active craving returns `200`; creation returns `201`. Resolving as `smoked` atomically records one cigarette at the current price. Repeating the same outcome is safe; choosing a different outcome afterward returns `409`. Triggers are an empty string, `coffee`, `stress`, `meal`, `social`, `boredom` or `other`.

Reminder times use `HH:MM` in the account time zone. An enabled reminder inside quiet hours returns `400 reminder_quiet_conflict`. The coaching CSV covers the last 30 completed days with quantities, confirmations, goals and historical costs.


### Connected sessions

`GET /api/tokens` lists only unexpired access. Each entry includes `kind` (`api`, `session`, or `legacy`), `client` (`web`, `android`, or null), and `created_at` (null for older entries), alongside its existing fields. No secret or digest is returned.

`DELETE /api/sessions/others` returns 204 and revokes this account’s explicitly typed sessions except the token making the request. It preserves API keys and ambiguous legacy entries. Repeated calls are harmless. Individual revocation remains available through `DELETE /api/tokens/{id}`.

The web settings show API keys separately from a collapsed **Connected devices** section. Each login creates a session; the list does not identify unique physical devices. Old entries named `Session` have an ambiguous type and appear under **Older access**, with individual revocation only. The additive migration preserves existing tokens and their expiry dates.


### Account deletion

`DELETE /api/me` requires the account bearer token and `{"password":"CURRENT_PASSWORD","confirm":true}`. Incorrect confirmation/password returns 400, missing or revoked authentication returns 401, and repeated attempts are subject to the existing authentication rate limit. Success returns 204.

One SQLite transaction deletes cravings, daily confirmations, the journey/reference/reminders, consumption entries, all tokens, push subscriptions/outbox entries, synchronization revisions and the user record. Existing SSE clients detect token revocation on their next check. Other accounts are unaffected. Account IDs are never reused: a global numeric high-water mark prevents an old in-flight request from targeting a newly registered account.

Deletion removes records from the active application database. Administrator backups and CSV files previously exported outside the application are not retroactively erased; their retention is managed separately. IP-based rate-limit counters are shared security metadata, not attached to a user account.

## Administrator and email workflows

Administrators use session bearer tokens with `/api/admin/users`, `/api/admin/invitations`, `/api/admin/smtp` and `/api/admin/profile`. Personal API keys cannot administer the instance. An administrator account cannot access consumption APIs. `/api/me` includes `role`, `language`, `email` and `email_verified`.

`/api/config.email_required` tells clients whether registration needs an email address. When true, `POST /api/auth/register` returns `activation_required: true` and a message rather than a token; the client must not consider the user signed in. A verified account can use the normal login route afterwards.

Public recovery routes are `POST /api/auth/forgot-password`, `POST /api/auth/resend-activation` and `POST /api/auth/complete`. A signed-in user can add a recovery email with `POST /api/account/email` and their current password. See the [OpenAPI contract](openapi.yaml) and [administration guide](../deployment/administration.md) for payloads, expiration, session revocation and SMTP behavior.

SMTP responses include `managed_by_environment`. When true, environment variables own the effective settings: `PUT /api/admin/smtp` returns HTTP 409 and test delivery still uses the effective configuration. The SMTP password is never returned.

## Consumption exports

Authenticated users can request `GET /api/export.csv` or `GET /api/report.html` with optional inclusive `start` and `end` dates. Both use the account time zone and accept 1–366 days, ending no later than today. The default is the last 30 days. The HTML report uses the account language, contains no name or account identifier, and can be printed to PDF by a browser. Both responses are private, user-scoped attachments with `Cache-Control: no-store`; send the bearer token in the Authorization header, never in a shared URL. See the [OpenAPI contract](openapi.yaml) and [user guide](../user-guide/usage.md#download-and-share-consumption-records).
