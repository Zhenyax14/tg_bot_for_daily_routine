<div align="center">

# Telegram Daily Bot

Bot de Telegram que publica mensajes programados a horas fijas en un grupo.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose_v2-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![Telegram](https://img.shields.io/badge/python--telegram--bot-21.4-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://python-telegram-bot.org/)
[![APScheduler](https://img.shields.io/badge/APScheduler-3.10.4-4B8BBE?style=for-the-badge&logo=clockify&logoColor=white)](https://apscheduler.readthedocs.io/)

[![Arquitectura](https://img.shields.io/badge/arquitectura-hexagonal-7F77DD?style=flat-square)](#arquitectura)
[![Conventional Commits](https://img.shields.io/badge/commits-conventional-1D9E75?style=flat-square&logo=conventionalcommits&logoColor=white)](https://www.conventionalcommits.org/)
[![Versión](https://img.shields.io/badge/versi%C3%B3n-1.0.0-888780?style=flat-square)](../CHANGELOG.md)

[English](../readme.md) · **Español**

</div>

---

Implementado con arquitectura hexagonal (puertos y adaptadores) y patrones tácticos de DDD. El núcleo de la aplicación no conoce ni Telegram ni el planificador: ambos son detalles reemplazables.

## Requisitos

- Python 3.11+
- Docker y Docker Compose v2 (para el despliegue)
- Un token de bot de Telegram, obtenido en [@BotFather](https://t.me/BotFather)

## Arranque rápido

```bash
git clone https://github.com/Zhenyax14/tg_bot_for_daily_routine.git && cd tg_bot_for_daily_routine
cp docker/.env.example .env      # y rellena los valores
docker compose -f docker/docker-compose.yaml up -d --build
docker compose -f docker/docker-compose.yaml logs -f
```

---

## Arquitectura

La regla que gobierna todo el diseño: **las dependencias apuntan hacia dentro**.

```
┌─ Infraestructura ────────────────────────────────┐
│   Telegram · APScheduler · repositorio estático  │
│                                                  │
│   ┌─ Aplicación ─────────────────────────────┐   │
│   │   Casos de uso · puertos                 │   │
│   │                                          │   │
│   │   ┌─ Dominio ───────────────────────┐    │   │
│   │   │   DailyTime · ScheduledMessage  │    │   │
│   │   │   No importa nada               │    │   │
│   │   └─────────────────────────────────┘    │   │
│   └──────────────────────────────────────────┘   │
└──────────────────────────────────────────────────┘
```

| Capa | Puede importar | Contiene |
|---|---|---|
| `domain` | nada (solo stdlib) | Value objects, entidades, interfaces de repositorio |
| `application` | `domain` | Casos de uso y puertos |
| `infrastructure` | `domain`, `application` | Adaptadores concretos |
| `main.py` | todo | Composition root |

`main.py` es el único fichero que instancia clases concretas. Todo lo demás recibe sus dependencias por constructor y depende únicamente de definiciones `Protocol`.

### Estructura del proyecto

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
├── docs/
│   └── README.es.md
├── .env                                            # valores reales, fuera de git
├── .dockerignore
└── README.md
```

### Componentes

**`DailyTime`** — value object inmutable. Valida en el constructor que la hora esté en rango, de modo que un `DailyTime` inválido no puede existir. Único punto del proyecto que parsea el formato `HH:MM`.

**`ScheduledMessage`** — entidad. Lleva su propio `id`: dos mensajes con idéntico texto y hora siguen siendo distintos.

**`MessageRepository`** — interfaz declarada en el dominio, implementada en infraestructura (inversión de dependencias).

**`Notifier`** — puerto de salida para el envío. Dos implementaciones: `TelegramNotifier` y `ConsoleNotifier`.

**`Scheduler`** — puerto de salida para la programación. Expone `schedule_daily`, `start` y `shutdown`; el vocabulario de APScheduler (`trigger`, `misfire_grace_time`) nunca cruza esta frontera.

**`SendMessage`** — único caso de uso de envío. Toda salida del sistema pasa por él, incluido el mensaje de arranque.

**`ScheduleDailyMessages`** — recorre el repositorio y registra un job por mensaje. Añadir mensajes no modifica este código.

### Flujo de ejecución

```
APScheduler dispara el job
        │
        ▼
clausura creada por ScheduleDailyMessages._job_for
        │
        ▼
SendMessage.execute(text)
        │
        ▼
Notifier.send(text)        ← TelegramNotifier o ConsoleNotifier
```

El caso de uso desconoce qué implementación hay detrás del puerto. Esa indirección es lo que permite ejercitar el flujo completo sin token ni acceso a la red.

---

## Configuración

Variables leídas por `Settings.from_env()`. Se validan todas de una vez al arrancar; si falta alguna obligatoria, el proceso sale con código `1` listando **todas** las que faltan.

| Variable | Obligatoria | Por defecto | Descripción |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | sí | — | Token de @BotFather |
| `CHAT_ID` | sí | — | ID del grupo. Los supergrupos empiezan por `-100` |
| `THREAD_ID` | no | vacío | ID del tema. Dejar vacío en grupos sin temas |
| `TZ` | no | `Europe/Madrid` | Zona horaria del planificador y del contenedor |
| `DRY_RUN` | no | `false` | Si es `1`/`true`/`yes`/`on`, usa `ConsoleNotifier` y no sale a la red |
| `STARTUP_MESSAGE` | no | `Инициализируюсь...` | Mensaje enviado al arrancar |

Ejemplo de `.env` en la raíz del proyecto:

```
TELEGRAM_BOT_TOKEN=1234567890:AAF-xxxxxxxxxxxxxxxxxxxxxxxxxxxx
CHAT_ID=-1001234567890
THREAD_ID=
```

Ejecuta `chmod 600 .env` y asegúrate de que está listado en `.gitignore`. Un token filtrado al historial de git hay que revocarlo.

### Mensajes programados

Definidos como datos en `infrastructure/persistence/static_message_repository.py`:

```python
_MESSAGES: tuple[tuple[str, str, str], ...] = (
    ("morning-greeting", "07:00", "..."),
    ("game-chance",      "07:15", "..."),
    ("good-night",       "22:00", "..."),
)
```

Añadir un mensaje es una línea. El `id` debe ser único: se usa como identificador del job en APScheduler.

---

## Desarrollo local

```bash
cd app
python -m venv ../.venv && source ../.venv/bin/activate
pip install -r ../docker/requirements.txt
```

Los imports son absolutos desde `app`, así que hay que lanzar desde ese directorio (o exportar `PYTHONPATH=app`).

### Arranque en seco, sin token ni red

```bash
DRY_RUN=1 TELEGRAM_BOT_TOKEN=x CHAT_ID=x python -u main.py
```

Debe registrar los tres jobs, imprimir `[DRY-RUN] <mensaje de arranque>` y quedar a la espera. `Ctrl+C` cierra limpiamente.

### Arranque real

```bash
set -a; source ../.env; set +a
unset DRY_RUN
python -u main.py
```

### Comprobaciones

Verificación de credenciales sin arrancar la aplicación:

```bash
set -a; source .env; set +a
curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
  -d chat_id="$CHAT_ID" -d text="ping"
```

`"ok":true` confirma que token y chat son correctos.

---

## Docker

El contexto de build es la **raíz del proyecto**, porque el `Dockerfile` vive en `docker` pero necesita copiar `app`. Las rutas relativas del compose (`context: ..`, `env_file: ../.env`) se resuelven respecto al fichero compose, no respecto al directorio actual.

```bash
# Desde la raíz
docker compose -f docker/docker-compose.yaml up -d --build
docker compose -f docker/docker-compose.yaml logs -f
docker compose -f docker/docker-compose.yaml down

# Desde docker/, sin -f
cd docker && docker compose up -d --build
```

Alias recomendado:

```bash
alias dcb='docker compose -f /ruta/a/tg_bot_for_daily_routine/docker/docker-compose.yaml'
```

### Verificación

```bash
# Configuración resuelta, con las variables expandidas
dcb config

# Las variables llegan realmente al contenedor
dcb run --rm --entrypoint env bot | grep -E 'TOKEN|CHAT|THREAD|TZ'

# El árbol completo llegó a la imagen
dcb run --rm --entrypoint sh bot -c "find . -name '*.py' | sort"

# No corre como root
dcb run --rm --entrypoint id bot

# Arranque en seco dentro del contenedor, sin tocar el .env
DRY_RUN=1 dcb run --rm -e DRY_RUN bot

# Apagado limpio: debe tardar menos de 1s, no los 5 del grace period
time dcb down
```

### Detalles de la imagen

- `PYTHONPATH=/app` — necesario para que resuelvan los imports absolutos entre paquetes.
- `CMD` en *exec form* — Python corre como PID 1 y recibe `SIGTERM` directamente, que es lo que hace funcionar el apagado limpio.
- Usuario no root (`bot`, uid 1000).
- Rotación de logs: 3 ficheros de 10 MB.

---

## Operación

Los logs siguen el formato `timestamp NIVEL logger | mensaje`. Líneas que conviene conocer:

| Línea | Significado |
|---|---|
| `Programado <id> a las HH:MM` | Job registrado correctamente |
| `Enviado: <texto>` | Mensaje entregado a Telegram |
| `Fallo al enviar ...` | Error de la API; el bot sigue vivo |
| `Faltan variables de entorno: ...` | Configuración incompleta, sale con código 1 |
| `Parado limpiamente` | `SIGTERM`/`SIGINT` procesado correctamente |

Diagnóstico de errores de envío:

| Error de Telegram | Causa |
|---|---|
| `chat not found` | `CHAT_ID` incorrecto — recuerda el prefijo `-100` en supergrupos |
| `Unauthorized` | Token inválido o revocado |
| `message thread not found` | `THREAD_ID` no hace falta; déjalo vacío |

Con `restart: unless-stopped`, un fallo de configuración provoca un bucle de reinicios. Los logs lo delatan repitiendo el mismo error: no lo confundas con un problema de red.

---

## Decisiones de diseño

**APScheduler en lugar de `schedule`.** La versión original movía `schedule` desde un bucle `while True` con `sleep(1)` y lambdas que llamaban a `asyncio.create_task`. APScheduler es async nativo: acepta corrutinas directamente y elimina por completo el bucle de sondeo.

**Sin ventana de silencio nocturna.** Existía para silenciar los mensajes recurrentes por la noche. Al quedar solo mensajes diarios a hora fija, perdió su propósito. La implementación original estaba rota de todos modos: el rango 22:00–07:00 cruza medianoche, así que `inicio <= ahora <= fin` nunca se cumplía.

**`ConsoleNotifier` va en producción.** No es código de test: vive en `infrastructure/` y se selecciona por configuración. Permite validar el cableado completo en cualquier entorno sin efectos secundarios.

**Captura de `TelegramError`, no de `Exception`.** Un `except Exception` genérico oculta bugs propios disfrazados de fallos de red.

**Sin mensajes por intervalo.** Requerirían un value object `Interval`, un método `schedule_interval` en el puerto y reintroducir la lógica de horas de silencio. Se omiten deliberadamente hasta que hagan falta.

---

## Convención de commits

[Conventional Commits](https://www.conventionalcommits.org/), usando el subdominio como scope (no la capa):

```
feat(scheduling): schedule messages through Scheduler port
refactor(config): centralize environment validation in Settings
build(docker): adapt image to layered structure
```

Los commits son *vertical slices*: cada uno atraviesa las capas que requiera un cambio de comportamiento. Un commit por capa produciría estados intermedios que no arrancan y rompería `git bisect`.

---