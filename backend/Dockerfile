# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv/app

RUN groupadd --system app && useradd --system --gid app --home-dir /srv/app app

COPY requirements.txt requirements-dev.txt ./
RUN pip install -r requirements.txt

COPY pyproject.toml alembic.ini ./
COPY app ./app
COPY migrations ./migrations

RUN mkdir -p /srv/app/storage && chown -R app:app /srv/app
USER app

EXPOSE 8000

FROM base AS dev
USER root
RUN pip install -r requirements-dev.txt
USER app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

FROM base AS production
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
