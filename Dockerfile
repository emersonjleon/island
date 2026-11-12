# Production image: one image, two processes (web and game host).
# Railway (deploy/railway/*.json) or any Docker host picks the process by start command.

# 1) Build the browser client into static/dist/.
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# 2) Python app.
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends gettext \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . .
RUN pip install .
COPY --from=frontend /app/static/dist/ static/dist/
# Translations and static files are baked into the image. The secret here is a throwaway
# that only lets prod settings load; set the real DJANGO_SECRET_KEY on the host.
RUN python manage.py compilemessages \
    && DJANGO_SETTINGS_MODULE=config.settings.prod DJANGO_SECRET_KEY=collectstatic-only \
       python manage.py collectstatic --noinput
ENV DJANGO_SETTINGS_MODULE=config.settings.prod
EXPOSE 8000
# Web process by default. The game host runs the same image with:
#   python manage.py run_gamehost
CMD daphne -b 0.0.0.0 -p ${PORT:-8000} config.asgi:application
