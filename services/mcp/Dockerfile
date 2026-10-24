FROM ghcr.io/astral-sh/uv:0.13.5 AS uv
FROM python:3.15.1-slim
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY packages/ packages/
COPY services/ services/
COPY config/categories.json config/categories.json
COPY config/mcp-evaluation.json config/mcp-evaluation.json
RUN uv sync --locked --no-dev --package newsloom-mcp
USER 65532:65532
EXPOSE 8000
ENTRYPOINT ["/app/.venv/bin/newsloom-mcp"]
