FROM ghcr.io/astral-sh/uv:0.13.5 AS uv
FROM python:3.15.1-slim
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENV TIKTOKEN_CACHE_DIR=/opt/tiktoken
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY packages/ packages/
COPY services/ services/
RUN uv sync --locked --no-dev --package newsloom-briefing
RUN /app/.venv/bin/python -c "import tiktoken; tiktoken.get_encoding('o200k_base')" && chmod -R a+rX /opt/tiktoken
USER 65532:65532
ENTRYPOINT ["/app/.venv/bin/newsloom-briefing"]
