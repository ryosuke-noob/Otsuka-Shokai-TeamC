# syntax=docker/dockerfile:1.4
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app

COPY pyproject.toml pyproject.toml

# system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates ffmpeg libsndfile1 build-essential && \
    rm -rf /var/lib/apt/lists/*

ARG TORCH_CUDA=cu125

# create venv and install torch (CUDA variant via TORCH_CUDA) and openai-whisper
RUN python -m venv /app/.venv && \
    /app/.venv/bin/python -m pip install --upgrade pip setuptools wheel && \
    /app/.venv/bin/python -m pip install --index-url https://download.pytorch.org/whl/${TORCH_CUDA} \
    torch torchvision torchaudio --extra-index-url https://pypi.org/simple && \
    /app/.venv/bin/python -m pip install --no-cache-dir -U openai-whisper numpy soundfile

COPY preload_whisper.py .
RUN /app/.venv/bin/python preload_whisper.py

COPY . .

ENV PYTHONPATH=/app/src
ENV PATH="/app/.venv/bin:${PATH}"

EXPOSE 8501

CMD ["/bin/sh", "-c", "\
    uv sync && \
    uv run -- streamlit run src/app/app.py \
    --server.address 0.0.0.0 \
    --server.port ${PORT:-8501} \
    --server.headless true \
    --server.runOnSave false \
    --server.fileWatcherType none \
    "]