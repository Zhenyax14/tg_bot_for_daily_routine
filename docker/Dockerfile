FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Europe/Madrid

# Zona horaria: slim no trae la base de datos de timezones
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Deps primero: cachea la capa mientras no cambie requirements
COPY docker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Usuario no root
RUN useradd -m -u 1000 bot
COPY --chown=bot:bot app/ ./
USER bot

CMD ["python", "appAsync1.1.py"]