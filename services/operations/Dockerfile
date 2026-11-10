FROM ghcr.io/astral-sh/uv:0.13.5 AS uv
FROM python:3.15.1-slim
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg postgresql-common \
    && /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y \
    && apt-get install -y --no-install-recommends postgresql-client-18 \
    && apt-get purge -y curl gnupg && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY packages/ packages/
COPY services/ services/
RUN uv sync --locked --no-dev --package newsloom-operations
# Fails the build if the async blob transport or pg_dump is missing from the image.
RUN /app/.venv/bin/python -c "from azure.storage.blob.aio import ContainerClient; ContainerClient('https://build.blob.core.windows.net', 'check')" \
    && pg_dump --version | grep -q ' 18\.'
USER 65532:65532
ENTRYPOINT ["/app/.venv/bin/newsloom-operations"]
