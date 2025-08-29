# syntax=docker/dockerfile:1.4
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim
WORKDIR /app

# system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates ffmpeg libsndfile1 build-essential && \
    rm -rf /var/lib/apt/lists/*

ARG TORCH_CUDA=cu125

COPY pyproject.toml pyproject.toml
COPY uv.lock uv.lock
RUN uv sync --frozen

COPY preload_whisper.py .
RUN uv run -- python preload_whisper.py

COPY . .

ENV PYTHONPATH=/app/src
ENV PATH="/app/.venv/bin:${PATH}"

EXPOSE 8501

CMD ["uv","run","--","streamlit","run","src/app/app.py","--server.address","0.0.0.0","--server.port","8501","--server.headless","true","--server.runOnSave","false","--server.fileWatcherType","none"]
