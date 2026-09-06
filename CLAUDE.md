# CLAUDE.md

Guidance for working on **bot2** — a personal Telegram bot with a web admin panel.
This file documents the architecture, conventions, current state, and (in detail)
the **price-alerts** feature.

---

## 1. What this project is

A Telegram bot that posts scheduled daily messages to a group, announces
Spanish/Russian public holidays, answers a couple of commands (`/time`,
`/holidays`), ships a small web admin panel, and posts **price alerts**
(sharp intraday moves on stocks / ETFs / FX) to a dedicated thread.

- **Repo:** `Zhenyax14/bot2` (GitHub)
- **Runtime:** Python 3.11, `python-telegram-bot`, APScheduler, aiohttp,
  asyncpg, Jinja2, bcrypt, httpx
- **Datastore:** PostgreSQL 17
- **Deploy:** Docker Compose on a Proxmox **unprivileged LXC** (`tgbot`,
  CTID 101, `192.168.1.204`)

---

## 2. Architecture & conventions (READ FIRST)

### Hexagonal + tactical DDD

Dependencies point **inward**. Four layers:

| Layer | May import | Contains |
|---|---|---|
| `domain` | stdlib only | Value objects, entities, domain services, repository interfaces (`Protocol`) |
| `application` | `domain` | Use cases, ports (`Protocol`), application services |
| `infrastructure` | `domain`, `application` | Concrete adapters (Postgres, Telegram, HTTP providers, web) |
| `main.py` | everything | Composition root — the **only** place that instantiates concrete classes |

Everything receives its dependencies by constructor and depends only on
`Protocol` definitions. A new external data source = a **new adapter behind an
existing port**, never a change to domain/application logic. This pattern has
been validated repeatedly (holidays, municipality directory, quote providers).

### Import convention (critical)

- `PYTHONPATH=app` locally, `/app` in Docker; container `WORKDIR=/app`.
- Imports are **prefix-free**: `from domain...`, `from application...`,
  `from infrastructure...` — **never** `from app.domain...`.
- In PyCharm, mark `app` as **Sources Root** so imports resolve.

### `resources/` placement (easy to get wrong)

`resources/` sits **directly under `app/`** (next to `domain/`, `application/`,
`infrastructure/`), so the Dockerfile's existing `COPY app/ ./` picks it up with
no build change.

```
app/
├── domain/
├── application/
├── infrastructure/
├── config/
├── resources/
│   ├── views/           # Jinja2 templates
│   └── static/          # css / js served at /static
└── main.py
```

### Language rules

- **Code, routes, filenames, commits, comments, docs → English. Always.**
- **Admin UI copy → Spanish** (e.g. "Inicio", "Ubicación", "Buscar",
  "Localidad activa"). The sidebar section is labelled "Ubicación" but its route
  and files are `location`.
- **Bot's Telegram output → Russian** (holiday greetings, price alerts).
- **App display name → "Bot"** (previously "BRAINBIZZ" during design; renamed).

### File placement gotcha (has bitten us repeatedly)

Files go under `app/...` **from the repo root** (`~/PycharmProjects/bot2/`),
**not** from `docker/`. Running `ls app/...` while `cd`'d into `docker/` reports
a false "everything is missing". Always verify from the repo root:

```bash
cd ~/PycharmProjects/bot2
for f in app/path/one.py app/path/two.py; do
  [ -f "$f" ] && echo "OK   $f" || echo "MISSING $f"
done
```

### Commit style

Conventional Commits, using the **subdomain** as scope (not the layer), e.g.
`feat(admin): dashboard with sidebar navigation`. Commits are vertical slices
(cross layers as needed) so every commit builds.

---

## 3. Deployment / Docker

- Compose file: `bot2/docker/docker-compose.yaml`; `.env` at **repo root**
  (`../.env` from the compose file). Services: `bot` + `postgres:17`, volume
  `pgdata`.
- Web panel is published on **host 8081** → container 8080
  (`"8081:8080"`; internal `WEB_PORT` stays 8080). Panel at
  `http://192.168.1.204:8081`.
- **`requirements.txt` must contain:** `python-telegram-bot`, `apscheduler`,
  `httpx`, `tzdata`, `aiohttp`, `asyncpg`, `bcrypt`, `jinja2`. (Each missing one
  caused a `ModuleNotFoundError` cascade in the past.)

Common commands:

```bash
# Rebuild after code changes (use --no-cache when in doubt)
docker compose -f docker/docker-compose.yaml build --no-cache bot
docker compose -f docker/docker-compose.yaml up -d
docker compose -f docker/docker-compose.yaml logs -f

# Dry run (no token / no network)
DRY_RUN=1 docker compose -f docker/docker-compose.yaml run --rm -e DRY_RUN bot
```

**Browser cache gotcha:** after editing CSS/views, hard-reload with
**Ctrl+Shift+R**. A stale cached page once looked completely unstyled while
`curl -i http://localhost:8081/static/css/app.css` returned `200 OK` — always
`curl` the asset before assuming a backend bug.

**Debugging import cascades** — verify every `from ... import` in `main.py`
resolves before rebuilding:

```bash
PYTHONPATH=app python3 -c "
import importlib.util
for line in open('app/main.py'):
    line = line.strip()
    if line.startswith('from ') and ' import ' in line:
        mod = line.split()[1]
        if importlib.util.find_spec(mod) is None:
            print('MISSING:', mod)
print('--- done ---')
"
```

Deployment specifics (LXC creation, the mandatory AppArmor workaround, scheduled
shutdown/startup cron on the node) live in `tgbot-lxc-deploy-en.md`. Not repeated
here.

---

## 4. Configuration (`Settings.from_env()`)

All env vars are read and validated **once** at startup; if a required one is
missing the process exits with code 1 listing all missing vars.

`DATABASE_URL` is **built programmatically** from `POSTGRES_*` components — it is
**never** stored directly in `.env` (that caused a password desync bug). Single
source of truth for the DB password is `POSTGRES_PASSWORD`.

Key vars:

| Var | Required | Default | Notes |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | yes | — | from @BotFather |
| `CHAT_ID` | yes | — | supergroup, starts with `-100` |
| `THREAD_ID` | no | empty | topic id for the daily messages thread |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | yes | — | DB creds (URL built from these) |
| `POSTGRES_HOST` / `POSTGRES_PORT` | no | `postgres` / `5432` | |
| `SPAIN_MUNICIPIO` | no | `03031` (Benidorm) | default INE municipality |
| `WEB_HOST` / `WEB_PORT` | no | `0.0.0.0` / `8080` | panel bind |
| `ADMIN_USER` / `ADMIN_PASSWORD` | `ADMIN_PASSWORD` yes | `admin` / — | seeds the first admin (only if `users` is empty) |
| `ADMIN_ROLE` | no | `admin` | role of the seeded admin |
| `ADMIN_EMAIL` | no | `admin@example.com` | email of the seeded admin |
| `TZ` | no | `Europe/Madrid` | |
| `DRY_RUN` | no | `false` | `1/true/yes/on` → ConsoleNotifier, no network |
| `STARTUP_MESSAGE` | no | `Инициализируюсь...` | sent on every startup |
| `PRICE_ALERTS_THREAD_ID` | no | `331017` | topic id for price-alert messages, same group as `CHAT_ID` |

---

## 5. Database schema

Applied idempotently on every startup (`CREATE TABLE IF NOT EXISTS` +
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`). Safe on the already-deployed DB.

- **`location`** — single-row table (`id boolean PK DEFAULT true CHECK (id)`,
  `ine text`, `nombre text`). Holds the active Spanish municipality.
- **`users`** — `id serial PK`, `name text UNIQUE`, `password_hash text`,
  `role text`, `avatar text`, `email text` (+ partial unique index
  `WHERE email IS NOT NULL`).
- **`instrument_disabled`** — `symbol text PK`. Presence of a row = that
  instrument is disabled for price alerts. Absence = enabled (the default);
  this way adding/removing instruments from the code catalog never needs a
  migration. See §8.7.

Passwords are bcrypt (salted, irreversible). Never stored in cleartext.

---

## 6. What is DONE (web panel & auth)

### Location by municipality name (festivos.io)

Single ES data source: `festivos.io /v1/ref/municipios.json` (~8,132
municipalities, `ine` as 5-digit text). User types a name; a unique match saves
directly, an ambiguous one shows candidates. The old postal-code approach and
its `cerocoma` dependency were removed entirely.

- `domain/value_objects/municipality.py` — `Municipality(ine, name)`; identity
  is the 5-digit INE only (`name` is `compare=False`).
- `application/ports/municipality_directory.py` — `MunicipalityDirectory` port +
  `MunicipalitySearchResult`.
- `infrastructure/location/festivos_io_municipality_directory.py` — adapter,
  in-memory cached (fetches the list once per process).

### Users, bcrypt, sessions, admin bootstrap

Replaced Basic Auth with a real login (username + password + cookie session).
Only `role == "admin"` may enter the panel.

- `domain/value_objects/user_role.py` — free-text, normalized, max 50 chars (no
  closed enum; concrete roles are decided by the feature that uses them).
- `domain/value_objects/email.py` — simple validated/normalized email VO.
- `domain/entities/user.py` — `User(id, name, email, password_hash, role, avatar)`.
- `domain/repositories/user_repository.py` — `UserRepository` protocol
  (`add`, `get_by_name`, `get_by_email`, `list_all`, `update`, `delete`, `count`).
- `application/ports/password_hasher.py` — `PasswordHasher` protocol.
- `infrastructure/security/bcrypt_password_hasher.py` — `BcryptPasswordHasher`.
- `application/services/user_service.py` — `UserService` (`create`,
  `authenticate`, `get_by_name`, `register` + `DuplicateUser`).
- `application/use_cases/bootstrap_admin_user.py` — seeds the first admin from
  env **only if the users table is empty** (never resets on later restarts).
- `infrastructure/persistence/postgres_user_repository.py`.
- `infrastructure/web/session_store.py` — in-memory `SessionStore`
  (token → username; lost on restart, which is fine).

### Jinja2 view system (Laravel-style)

- Views are `.html` files under `resources/views/`, static assets under
  `resources/static/`. Jinja2 **autoescape** is on (free XSS protection —
  replaced manual `html.escape()` calls).
- `infrastructure/web/view_renderer.py` — `ViewRenderer` wraps Jinja2, loads
  from `resources/views` via `parents[2]`; subfolders are addressed with `/`
  (e.g. `admin/layout.html`). Laravel-style `{% extends %}` / `{% block %}`.
- An older in-Python `templates.py` approach was **deleted**.

### Public landing + admin panel (yellow "BrainBizz"-inspired UI)

- Aesthetic: yellow accent `#f4b400`, fonts **Space Grotesk** (display) +
  **Inter** (body), dark hero. (Frontend built after reading
  `frontend-design` skill; stock photos were **not** cloned — abstract gradients
  used instead; marketing copy rewritten.)
- **Routing:**
  - `/` — public landing. Header shows **"Entrar"** (no session) or
    **"Panel" + "Salir"** (session).
  - `/login`, `/logout` — public.
  - `/admin` — **dashboard** (protected).
  - `/admin/location` (GET/POST) and `/admin/location/confirm` (POST) — location
    section (protected).
  - `/admin/alerts` (GET/POST) — enable/disable price-alert instruments
    (protected, added with the price-alerts feature; see §8.7).
  - `/static/...` — assets (excluded from auth middleware).
  - Public paths in middleware: `{"/", "/login", "/logout", "/health"}` +
    `/static/`.
- **Views layout:**
  ```
  resources/views/
  ├── layout.html          # public layout (landing/login)
  ├── landing.html
  ├── login.html
  └── admin/
      ├── layout.html      # admin shell: sidebar + topbar
      ├── dashboard.html
      ├── location.html
      └── candidates.html
  ```
- **Dashboard** (`/admin`): three cards — "Localidad activa", "Estado" (green dot
  via `.status-ok .dot`, colour `#28a745`), "Tiempo activo" (uptime). **No action
  button.**
- **Sidebar:** dark, fixed; nav items **"Inicio"** (`/admin`), **"Ubicación"**
  (`/admin/location`) and **"Alertas"** (`/admin/alerts`), active item
  highlighted yellow. Footer user-box: avatar
  circle (`user.avatar` image, else `user_initial`), "Bienvenido, {user_name}",
  and a logout icon button. Collapses to a horizontal bar on mobile.
- **Location** section: centered `.form-card`.
- **Sticky footer** on the public layout: `body` is a flex column,
  `min-height:100vh`, content expands to push the footer down.

### Uptime

- `application/services/uptime_service.py` — `UptimeService(monotonic)` with
  `mark_started()` and `uptime_human()` (`"3h 25m"`, `"2d 5h 7m"`). Uses
  `time.monotonic` (immune to system clock changes).
- `main.py` creates `UptimeService(time.monotonic)`, calls `mark_started()` in
  `post_init` **before** `scheduler.start()`, and passes it into
  `build_admin_app(...)`.
- `build_admin_app(location, municipality_directory, user_service, uptime_service)`.

### `build_admin_app` context

The auth middleware puts the authenticated `user` in `request["user"]`. A
`_user_context(request)` helper injects `user_name`, `user_initial`, `avatar`
into every admin template render (dashboard, location, candidates) so the
sidebar user-box renders everywhere.

---

## 7. ABANDONED: public registration

A public `/register` (role `user`, email required/unique, min 3-char name, min
8-char password, `DuplicateUser` check) **was fully built and tested, then
cancelled** by the user to pivot to price alerts. The `email` column and `Email`
VO were kept (harmless, and groundwork for a future password reset). No email
sending was ever implemented. If cleaning up: the `/register` route + `register.html`
can be removed; leave the `email` column and `Email` VO.

---

## 8. DONE (code-complete, pending live Telegram delivery test): price alerts

Posts sharp intraday price moves for stocks / ETFs / FX into a dedicated Telegram
thread. Fully implemented and wired into `main.py`; the whole pipeline (fetch →
policy → reference tracking → formatting) was verified against **live** Yahoo
Finance / MOEX data in a throwaway sandbox, reproducing the Tesla worked example
below exactly. Not yet verified against a real Telegram send (no bot token /
Postgres available in the sandbox that built this) — do that after the next
deploy.

### 8.1 Confirmed requirements (all decided with the user)

- **Instruments to track:** the "Magnificent 7" US stocks, two US ETFs, a few
  Russian (MOEX) stocks, and RUB FX pairs. See the catalog in §8.4.
- **Alert logic = chained ±5% trail, reset daily.** This is the core rule:
  - Each symbol has a **reference price**.
  - On the **first** price seen for a symbol on a given day (or at startup), the
    reference is set **silently** (it is the baseline, not a move).
  - When a new price differs from the reference by **≥ ±5%** (up **or** down, no
    time window), an alert **fires** AND the reference is **reset to the alerted
    price** (chained trail).
  - References **clear each calendar day**; the first price of the new day
    re-baselines silently.
  - The user explicitly wants the **full trail of every sharp move**, not
    anti-spam suppression. Worked example (Tesla, one day):
    `100 → 88` (**-12%**, alert, ref=88) → `83.6` (**-5%**, alert, ref=83.6) →
    `89.45` (**+7%**, alert, ref=89.45). A flat move (e.g. `88 → 91`, +1.7%) does
    NOT re-alert because it is < 5% from the current reference.
- **Destination:** a **new thread in the SAME group** as the bot's current
  `CHAT_ID`. Link `https://t.me/c/1390219899/331017` → group `-1001390219899`
  (add the `-100` prefix), `message_thread_id = 331017`. Reuse `TelegramNotifier`
  with this thread id.
- **Check frequency:** **every 5 minutes.** Hardware cost is negligible (a few MB
  RAM for in-memory references, ms of CPU, a handful of HTTP calls per cycle).
- **Data sources (all free, no API key):**
  - **US stocks/ETFs → Yahoo Finance** (unofficial public `v8/finance/chart`
    endpoint, no key, one request per symbol). **Not Stooq**: Stooq's public CSV
    (`/q/l/` and `/q/d/l/`) was verified working when this feature was designed,
    but by the time it was wired up (2026-09-06) Stooq had put a JS
    proof-of-work anti-bot challenge in front of the **entire site**, including
    those CSV endpoints — every plain HTTP request (curl included) now gets a
    404 or an HTML challenge page instead of data. Swapped to Yahoo Finance
    behind the same `QuoteProvider` port, per the "new source ⇒ new adapter"
    rule in §2. If Yahoo ever does the same, swap the adapter again — nothing
    else changes.
  - **RU stocks + FX → MOEX ISS** (`iss.moex.com`, free, no auth, delayed).

### 8.2 Verified external formats

- **Yahoo Finance:** `GET https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}`
  (plain ticker, e.g. `AAPL`, no suffix) with header `User-Agent: Mozilla/5.0`
  (requests with no UA get blocked). Current price is
  `chart.result[0].meta.regularMarketPrice` (JSON). One request per symbol — no
  working key-less batch endpoint (`v7/finance/quote?symbols=...` now returns
  `401 Unauthorized` without a crumb/cookie; not worth the complexity for 9
  symbols every 5 minutes).
- **MOEX ISS** returns JSON in **`columns` + `data`** blocks. Current price is the
  **`LAST`** column.
  - Shares (board TQBR):
    `/iss/engines/stock/markets/shares/boards/TQBR/securities/{SECID}.json?iss.only=marketdata&iss.meta=off`
  - FX (market `selt`, board CETS):
    `/iss/engines/currency/markets/selt/boards/CETS/securities/{SECID}.json?iss.only=marketdata&iss.meta=off`
  - FX SECIDs: `USD000UTSTOM` (USD/RUB), `EUR_RUB__TOM` (EUR/RUB),
    `CNYRUB_TOM` (CNY/RUB). **`EUR_RUB__TOM` has no live trades** (MOEX
    suspended EUR/RUB trading under EU sanctions) — `TRADINGSTATUS` is `N` and
    `LAST` is `null`, so `MoexQuoteProvider` correctly skips it forever (no
    error, just never alerts). Harmless to leave in the catalog; remove it if
    the dead weight bothers you.

### 8.3 DONE — files built, tested, and wired into `main.py`

All compile; pure domain/application logic (the Tesla trail, daily reset,
formatting) is covered by real unit tests; the adapters were exercised against
**live** Yahoo Finance / MOEX endpoints, fetching real quotes for the full
16-instrument catalog. Target paths (from repo root):

| File | Purpose |
|---|---|
| `app/domain/value_objects/instrument.py` | `Instrument(symbol, label, market, category, currency)`; `market ∈ {"us","ru","fx","crypto"}`, `category ∈ {"us_stock","us_etf","ru_stock","fx","crypto"}`, `currency ∈ {"$","₽"}` |
| `app/domain/value_objects/quote.py` | `Quote(symbol, price, at)`; `price > 0` |
| `app/domain/services/price_movement_policy.py` | `Movement(reference, current)` with `.percent`; `PriceMovementPolicy(threshold_percent=5.0)` → `is_significant()`, `movement()` |
| `app/application/ports/quote_provider.py` | `QuoteProvider` port: `fetch(instruments) -> quotes` |
| `app/application/services/reference_prices.py` | `ReferencePrices(today_provider)`: `reference_for(symbol)`, `set_reference(symbol, price)`, clears on day change |
| `app/application/use_cases/check_price_movements.py` | `CheckPriceMovements(instruments, provider, references, policy, alert)` — fetch → per quote: no ref ⇒ set baseline silently, else if significant ⇒ `await alert(instrument, movement)` + reset reference (alert exceptions are caught/logged per symbol so one failure doesn't skip the rest) |
| `app/infrastructure/quotes/movement_formatting.py` | `format_movement_alert(instrument, movement)` → Russian HTML: `🔺/🔻 <b>{label}</b>: {+/-X.X}%\n{ref:.2f} → {current:.2f}` |
| `app/infrastructure/quotes/yahoo_finance_quote_provider.py` | `YahooFinanceQuoteProvider` — one request per symbol against `v8/finance/chart`; reads `meta.regularMarketPrice`; **replaces the originally-planned `StooqQuoteProvider`** (see §8.1 — Stooq is now bot-gated) |
| `app/infrastructure/quotes/moex_quote_provider.py` | `MoexQuoteProvider` — per-instrument fetch; parses `columns`+`data`; picks `LAST`; `market=="fx"` uses the FX URL, else shares URL; null `LAST` (closed / suspended) → skipped |
| `app/infrastructure/quotes/routing_quote_provider.py` | `RoutingQuoteProvider(by_market)` — groups instruments by `market`, dispatches to the right adapter, **isolates failures** (one provider's exception is logged and does not tank the others) |
| `app/infrastructure/config/instruments.py` | `INSTRUMENTS` catalog (see §8.4) |

Also touched: `application/ports/scheduler.py` and
`infrastructure/scheduling/apscheduler_adapter.py` gained `schedule_interval`;
`infrastructure/notifiers/telegram.py` gained an optional `parse_mode`
constructor arg; `config/settings.py` gained `price_alerts_thread_id`; `main.py`
wires all of the above (`build_price_alerts_notifier`, `RoutingQuoteProvider`,
`ReferencePrices` keyed off `settings.timezone`, `CheckPriceMovements`,
`scheduler.schedule_interval("price-alerts", 5, ...)` registered before
`scheduler.start()`). `main.py`'s `_post_init` also sends a one-line Russian
confirmation ("✅ Система ценовых алертов запущена.") to the alerts thread on
every startup — cheap, permanent proof-of-life for this feature whenever the
bot restarts.

### 8.7 DONE — per-instrument enable/disable from the admin panel

The 28-instrument catalog above is code (`INSTRUMENTS`, static, changes need a
deploy), but **which of them actually trigger alerts** is a runtime setting
stored in Postgres and editable from `/admin/alerts` without restarting the bot.

- `domain/repositories/instrument_settings_repository.py` — `InstrumentSettingsRepository`
  protocol: `load_disabled_symbols()`, `set_enabled(symbol, enabled)`.
- `infrastructure/persistence/postgres_instrument_settings_repository.py` —
  Postgres adapter over the `instrument_disabled` table (see §5).
- `application/services/instrument_settings_service.py` —
  `InstrumentSettingsService(repository, catalog)`: caches the disabled set in
  memory (`load()` at startup, same pattern as `LocationService`), exposes
  `enabled_instruments()` / `is_enabled(symbol)` for fast sync reads and
  `set_enabled()` / `apply_enabled_symbols(set_of_symbols)` for writes.
- `application/use_cases/check_price_movements.py` was changed to take the
  `InstrumentSettingsService` instead of a fixed instrument list, and calls
  `enabled_instruments()` **on every 5-minute cycle** — so a checkbox toggled
  in the panel takes effect on the very next cycle, no redeploy needed.
- `infrastructure/web/admin_server.py` — new `/admin/alerts` GET/POST routes,
  `_alerts_context()` groups `INSTRUMENTS` by `category` using
  `_ALERT_CATEGORY_LABELS`/`_ALERT_CATEGORY_ORDER` (Spanish labels: "Acciones
  (Magníficas)", "Fondos (ETF)", "Acciones MOEX", "Divisas"). POST reads
  `data.getall("enabled")` (checked boxes only — HTML omits unchecked ones from
  the form) and calls `apply_enabled_symbols()` with that full set, so anything
  absent from the POST body is disabled.
- `resources/views/admin/alerts.html` + sidebar entry "Alertas" in
  `admin/layout.html`; CSS in `resources/static/css/app.css` under "alertas de
  precio" (`.alerts-card`, `.instrument-grid`, `.instrument-row`, etc.).
- `build_admin_app(...)` gained a required `instrument_settings` positional
  arg (5th, before the optional `renderer`) — update any direct caller if one
  is ever added outside `main.py`.
- Verified end-to-end with a fake repository + `aiohttp` `TestClient`: login
  gate, category grouping renders, POST persists exactly the checked set,
  a follow-up GET reflects it, and `CheckPriceMovements` skips fetching
  disabled symbols entirely (not just skips alerting on them).

### 8.4 Instrument catalog (`infrastructure/config/instruments.py`)

16 instruments. `symbol` must be what the market's provider expects
(us: plain Yahoo Finance ticker, no suffix; ru: MOEX TQBR SECID; fx: MOEX CETS
SECID). Labels are Russian for the alert text.

31 instruments across 5 categories (expanded 2026-09-06 from the original 16 at
the user's request, then again same day to add MSCI World + crypto — the
user's words: "super importante estos tres que son como 90% de mi
portafolio"; see §8.7 for how individual ones get turned on/off):

- **`us_stock` — Acciones (Magníficas), Yahoo Finance:** `AAPL` Apple, `MSFT`
  Microsoft, `GOOGL` Alphabet, `AMZN` Amazon, `NVDA` Nvidia, `META` Meta,
  `TSLA` Tesla, `AVGO` Broadcom *(the "8th Magnificent" — added alongside the
  original 7)*.
- **`us_etf` — Fondos (ETF), Yahoo Finance:** `SPY` S&P 500, `QQQ` Nasdaq 100,
  `DIA` Dow Jones, `IWM` Russell 2000, `URTH` MSCI World (iShares MSCI World
  ETF — Yahoo Finance has no bare "MSCI World index" ticker, this is the
  standard tradable proxy).
- **`crypto` — Criptomonedas, Yahoo Finance:** `BTC-USD` Bitcoin, `ETH-USD`
  Ethereum. Yahoo's `v8/finance/chart` endpoint (§8.2) covers crypto tickers
  transparently — same `YahooFinanceQuoteProvider`, no new adapter needed, just
  a new `market` routing key (`"crypto"`) pointed at the same provider instance
  in `main.py`. Unlike every other tracked market, **crypto trades 24/7** — no
  weekend silence, so expect this category to actually produce real alerts
  most often.
- **`ru_stock` — Acciones MOEX (TQBR), blue chips del índice IMOEX:** `SBER`
  Сбербанк, `GAZP` Газпром, `LKOH` Лукойл, `YDEX` Яндекс *(corrected from the
  delisted `YNDX`)*, `GMKN` Норникель, `ROSN` Роснефть, `NVTK` Новатэк, `TATN`
  Татнефть, `MTSS` МТС, `MGNT` Магнит, `PLZL` Полюс, `CHMF` Северсталь.
- **`fx` — Divisas (MOEX CETS):** `USD000UTSTOM` Доллар США / ₽, `CNYRUB_TOM`
  Юань / ₽, `TRYRUB_TOM` Турецкая лира / ₽, `KZTRUB_TOM` Тенге / ₽.
  **`EUR_RUB__TOM` was removed** (not disabled — dropped from the catalog
  entirely): confirmed via MOEX ISS it has zero live trades
  (`TRADINGSTATUS=N`, `LAST=null`) since MOEX suspended EUR/RUB trading under
  EU sanctions. Re-add it if MOEX ever resumes that pair.

### 8.5 OPEN — market-hours handling

Never decided; the job currently runs **24/7** (option (a) from the original
discussion: simplest, harmless). On weekends / closed markets prices don't
move so no alerts fire (MOEX `LAST` may be null → skipped; Yahoo Finance
returns the last close). Revisit only if the handful of extra HTTP calls
during closed hours ever actually matters — it currently doesn't.

### 8.6 Behavioral notes to remember

- **First cycle of the day is silent** per symbol (baseline set, no alert).
  Alerts begin from the second cycle once there's a reference to compare against.
- **Weekends / closed markets:** no movement ⇒ no alerts. Expect silence, not a
  bug.
- **In-memory references:** a bot restart re-baselines each symbol on the next
  fetch. Acceptable — it never invents fake jumps.
- **Not yet verified:** an actual Telegram send to the `331017` thread. The
  business logic was proven end-to-end against live market data in a sandbox
  that had no bot token / Postgres, so that last leg needs a real deploy.

---

## 9. Other pending / backlog

- **Moderator bot** — deferred; prerequisites now met (Postgres live, `users`
  table, roles). Rough sketch discussed: `ModerationPolicy` (domain service),
  `MemberStrikes` entity + `ModerationStateRepository` (Postgres, same pattern as
  `PostgresLocationRepository`), `ModerationGateway` port (separate from
  `Notifier`: mute/delete/ban via `restrict_chat_member` + `until_date`),
  `TelegramUpdateListener` driving adapter, `Duration` VO. Scope not yet chosen
  (new-member verification vs anti-flood+banned-words+strikes vs manual `/mute`).
  Would add a new sidebar section.
- **User management from the panel** — list/edit/delete users as a sidebar
  section. Offered, not built. `UserService.create()` exists at code level only.
- **Avatar** — column + model field exist; not surfaced/uploadable in the UI yet
  (sidebar falls back to the name initial).
- **Password reset by email** — deferred; `email` column is the groundwork. Would
  need a reset-tokens table + a `Mailer` port with an SMTP adapter.
- **`/weather`** (Open-Meteo) — mentioned long ago, never built.
- Registration cleanup (see §7).

### Infra TODOs (from the deployment doc)

- Create a sudo admin user; disable root SSH (`PermitRootLogin prohibit-password`).
- Verify the node's scheduled shutdown/startup cron fires autonomously.
- Take an initial `vzdump` backup.
- AppArmor workaround is **technical debt** — revisit when runc/Proxmox fix the
  incompatibility upstream (tracking `opencontainers/runc` #4972, #4968). Never
  flip the `unprivileged` flag on the existing CT (corrupts UID mappings; requires
  a full rebuild).
- Trim `requirements.txt` if any packages are no longer used.

---

## 10. Working method (how changes are made here)

- Every feature is a **complete vertical slice** across the layers, deployed after
  each step.
- New external data source ⇒ **new adapter behind an existing port** (never touch
  domain/application logic).
- All Python is built and **tested in a sandbox** (`py_compile` + real unit tests
  with fakes / `MockTransport`) **before** delivery; files are handed over at exact
  `app/...` paths and copied into the PyCharm project manually.
- Russian user-facing strings live in the **infrastructure** layer (formatting
  modules), out of domain/application.
- UI / routing changes touch **only** infrastructure (presentation);
  `main.py` and `build_admin_app`'s signature stay stable unless a genuinely new
  dependency is added.
- Keep responses/《changes》 minimal and consistent; separate app layers from
  Docker/deployment concerns.
