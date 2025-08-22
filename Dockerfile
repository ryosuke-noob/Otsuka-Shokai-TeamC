FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app

COPY . .

ENV PYTHONPATH=/app/src
ENV PATH="/app/.venv/bin:${PATH}"

EXPOSE 8501

CMD sh -lc "uv sync && uv run -- streamlit run src/app/app.py --server.address 0.0.0.0 --server.port ${PORT:-8501}"
