<div align="center">

# Telegram Daily Bot

A Telegram bot that publishes scheduled messages at fixed times in a group.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose_v2-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![Telegram](https://img.shields.io/badge/python--telegram--bot-21.4-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://python-telegram-bot.org/)
[![APScheduler](https://img.shields.io/badge/APScheduler-3.10.4-4B8BBE?style=for-the-badge&logo=clockify&logoColor=white)](https://apscheduler.readthedocs.io/)

[![Architecture](https://img.shields.io/badge/architecture-hexagonal-7F77DD?style=flat-square)](#architecture)
[![Conventional Commits](https://img.shields.io/badge/commits-conventional-1D9E75?style=flat-square&logo=conventionalcommits&logoColor=white)](https://www.conventionalcommits.org/)
[![Version](https://img.shields.io/badge/version-1.0.0-888780?style=flat-square)](CHANGELOG.md)

**English** · [Español](./docs/readme.es.md)

</div>

---

Built with hexagonal architecture (ports and adapters) and tactical DDD patterns. The application core knows nothing about Telegram or the scheduler: both are replaceable details.

## Requirements

- Python 3.11+
- Docker and Docker Compose v2 (for deployment)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

## Quick start

```bash
git clone https://github.com/Zhenyax14/tg_bot_for_daily_routine.git && cd tg_bot_for_daily_routine
cp docker/.env.example .env      # then fill in the values
docker compose -f docker/docker-compose.yaml up -d --build
docker compose -f docker/docker-compose.yaml logs -f
```

---

## Architecture

The rule that governs the whole design: **dependencies point inward**.

```
┌─ Infrastructure ─────────────────────────────────┐
│   Telegram · APScheduler · static repository     │
│                                                  │
│   ┌─ Application ────────────────────────────┐   │
│   │   Use cases · ports                      │   │
│   │                                          │   │
│   │   ┌─ Domain ────────────────────────┐    │   │
│   │   │   DailyTime · ScheduledMessage  │    │   │
│   │   │   Imports nothing               │    │   │
│   │   └─────────────────────────────────┘    │   │
│   └──────────────────────────────────────────┘   │
└──────────────────────────────────────────────────┘
```

| Layer | May import | Contains |
|---|---|---|
| `domain` | nothing (stdlib only) | Value objects, entities, repository interfaces |
| `application` | `domain` | Use cases and ports |
| `infrastructure` | `domain`, `application` | Concrete adapters |
| `main.py` | everything | Composition root |

`main.py` is the only file that instantiates concrete classes. Everything else receives its dependencies through the constructor and depends solely on `Protocol` definitions.

### Project layout

```
tg_bot_for_daily_routine/
├── app/
│   ├── main.py                                     
│   ├── config/
│   │   ├── errors.py                               
│   │   └── settings.py                             # Settings.from_env()
│   ├── domain/
│   │   ├── value_objects/daily_time.py             
│   │   ├── entities/scheduled_message.py           
│   │   └── repositories/message_repository.py      
│   ├── application/
│   │   ├── ports/
│   │   │   ├── notifier.py                         
│   │   │   └── scheduler.py                        
│   │   └── use_cases/
│   │       ├── send_message.py                     
│   │       └── schedule_daily_messages.py          
│   └── infrastructure/
│       ├── notifiers/
│       │   ├── telegram.py                         
│       │   └── console.py                          
│       ├── scheduling/apscheduler_adapter.py       
│       └── persistence/static_message_repository.py
├── docker/
│   ├── Dockerfile
│   ├── docker-compose.yaml
│   ├── requirements.txt
│   └── .env.example
├── .env                                            # real values, outside git
├── .dockerignore
├── README.md
└── README.es.md
```

### Components

**`DailyTime`** — immutable value object. Validates in the constructor that the time is within range, so an invalid `DailyTime` cannot exist. The only place in the project that parses the `HH:MM` format.

**`ScheduledMessage`** — entity. It carries its own `id`: two messages with identical text and time are still distinct.

**`MessageRepository`** — interface declared in the domain, implemented in infrastructure (dependency inversion).

**`Notifier`** — outbound port for delivery. Two implementations: `TelegramNotifier` and `ConsoleNotifier`.

**`Scheduler`** — outbound port for scheduling. Exposes `schedule_daily`, `start` and `shutdown`; APScheduler vocabulary (`trigger`, `misfire_grace_time`) never crosses this boundary.

**`SendMessage`** — the single delivery use case. Every outbound message goes through it, including the startup message.

**`ScheduleDailyMessages`** — iterates the repository and registers one job per message. Adding messages does not modify this code.

### Execution flow

```
APScheduler fires the job
        │
        ▼
closure created by ScheduleDailyMessages._job_for
        │
        ▼
SendMessage.execute(text)
        │
        ▼
Notifier.send(text)        ← TelegramNotifier or ConsoleNotifier
```

The use case has no idea which implementation sits behind the port. That indirection is what makes it possible to exercise the entire flow without a token or network access.

---

## Configuration

Variables read by `Settings.from_env()`. All are validated at once on startup; if a required one is missing, the process exits with code `1` listing **every** missing variable.

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | yes | — | Token from @BotFather |
| `CHAT_ID` | yes | — | Group ID. Supergroups start with `-100` |
| `THREAD_ID` | no | empty | Topic ID. Leave empty for groups without topics |
| `TZ` | no | `Europe/Madrid` | Timezone for the scheduler and the container |
| `DRY_RUN` | no | `false` | If `1`/`true`/`yes`/`on`, uses `ConsoleNotifier` and never hits the network |
| `STARTUP_MESSAGE` | no | `Инициализируюсь...` | Message sent on startup |

Example `.env` in the project root:

```
TELEGRAM_BOT_TOKEN=1234567890:AAF-xxxxxxxxxxxxxxxxxxxxxxxxxxxx
CHAT_ID=-1001234567890
THREAD_ID=
```

Run `chmod 600 .env` and make sure it is listed in `.gitignore`. A token leaked into git history has to be revoked.

### Scheduled messages

Defined as data in `infrastructure/persistence/static_message_repository.py`:

```python
_MESSAGES: tuple[tuple[str, str, str], ...] = (
    ("morning-greeting", "07:00", "..."),
    ("game-chance",      "07:15", "..."),
    ("good-night",       "22:00", "..."),
)
```

Adding a message is one line. The `id` must be unique: it is used as the APScheduler job identifier.

---

## Local development

```bash
cd app
python -m venv ../.venv && source ../.venv/bin/activate
pip install -r ../docker/requirements.txt
```

Imports are absolute from `app`, so run from that directory (or export `PYTHONPATH=app`).

### Dry run, no token and no network

```bash
DRY_RUN=1 TELEGRAM_BOT_TOKEN=x CHAT_ID=x python -u main.py
```

It should register the three jobs, print `[DRY-RUN] <startup message>` and wait. `Ctrl+C` shuts down cleanly.

### Real run

```bash
set -a; source ../.env; set +a
unset DRY_RUN
python -u main.py
```

### Checks

Credentials check without starting the application:

```bash
set -a; source .env; set +a
curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
  -d chat_id="$CHAT_ID" -d text="ping"
```

`"ok":true` confirms both token and chat are correct.

---

## Docker

The build context is the **project root**, because the `Dockerfile` lives in `docker` but needs to copy `app`. Relative paths inside the compose file (`context: ..`, `env_file: ../.env`) resolve against the compose file, not against your current directory.

```bash
# From the root
docker compose -f docker/docker-compose.yaml up -d --build
docker compose -f docker/docker-compose.yaml logs -f
docker compose -f docker/docker-compose.yaml down

# From docker/, no -f needed
cd docker && docker compose up -d --build
```

Suggested alias:

```bash
alias dcb='docker compose -f /path/to/tg_bot_for_daily_routine/docker/docker-compose.yaml'
```

### Verification

```bash
# Resolved configuration, with variables expanded
dcb config

# Variables actually reach the container
dcb run --rm --entrypoint env bot | grep -E 'TOKEN|CHAT|THREAD|TZ'

# The full tree made it into the image
dcb run --rm --entrypoint sh bot -c "find . -name '*.py' | sort"

# Not running as root
dcb run --rm --entrypoint id bot

# Dry run inside the container, without touching .env
DRY_RUN=1 dcb run --rm -e DRY_RUN bot

# Clean shutdown: should take under 1s, not the full 5s grace period
time dcb down
```

### Image details

- `PYTHONPATH=/app` — required for absolute imports across packages to resolve.
- Exec-form `CMD` — Python runs as PID 1 and receives `SIGTERM` directly, which is what makes graceful shutdown work.
- Non-root user (`bot`, uid 1000).
- Log rotation: 3 files of 10 MB.

---

## Operations

Logs follow the format `timestamp LEVEL logger | message`. Lines worth knowing:

| Line | Meaning |
|---|---|
| `Programado <id> a las HH:MM` | Job registered successfully |
| `Enviado: <text>` | Message delivered to Telegram |
| `Fallo al enviar ...` | API error; the bot stays alive |
| `Faltan variables de entorno: ...` | Incomplete configuration, exits with code 1 |
| `Parado limpiamente` | `SIGTERM`/`SIGINT` handled correctly |

Delivery error diagnosis:

| Telegram error | Cause |
|---|---|
| `chat not found` | Wrong `CHAT_ID` — remember the `-100` prefix on supergroups |
| `Unauthorized` | Invalid or revoked token |
| `message thread not found` | `THREAD_ID` is not needed; leave it empty |

With `restart: unless-stopped`, a configuration failure causes a restart loop. The logs give it away by repeating the same error — don't mistake it for a network problem.

---

## Design decisions

**APScheduler instead of `schedule`.** The original version drove `schedule` from a `while True` loop with `sleep(1)` and lambdas calling `asyncio.create_task`. APScheduler is async-native: it accepts coroutines directly and removes the polling loop entirely.

**No nightly quiet window.** It existed to silence recurring messages overnight. With only fixed-time daily messages left, it lost its purpose. The original implementation was broken anyway: the 22:00–07:00 range crosses midnight, so `start <= now <= end` was never true.

**`ConsoleNotifier` ships in production.** It is not test code: it lives in `infrastructure/` and is selected by configuration. It allows validating the full wiring in any environment with no side effects.

**Catching `TelegramError`, not `Exception`.** A bare `except Exception` hides your own bugs disguised as network failures.

**No interval-based messages.** They would require an `Interval` value object, a `schedule_interval` method on the port, and reintroducing quiet-hours logic. Deliberately omitted until actually needed.

---

## Commit convention

[Conventional Commits](https://www.conventionalcommits.org/), using the subdomain as scope (not the layer):

```
feat(scheduling): schedule messages through Scheduler port
refactor(config): centralize environment validation in Settings
build(docker): adapt image to layered structure
```

Commits are vertical slices: each one crosses whatever layers a behavioural change requires. One commit per layer would produce intermediate states that don't run and would break `git bisect`.

---
