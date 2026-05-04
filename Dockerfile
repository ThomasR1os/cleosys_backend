# Despliegue recomendado para SUNAT/Playwright (Chromium + dependencias del sistema).
# En Render: configure el servicio como "Docker" y apunte a este Dockerfile.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install-deps chromium \
    && playwright install chromium

COPY . .

ENV DJANGO_SETTINGS_MODULE=config.settings

# Un solo worker reduce RAM (Chromium); timeout alto por consultas a SUNAT.
CMD ["sh", "-c", "gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 1 --threads 1 --timeout 120"]
