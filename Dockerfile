FROM python:3.13-slim

# Non-root user: containers must not run as root on Cloud Run
RUN useradd --no-create-home --shell /bin/false appuser

WORKDIR /app

# Install pinned, hash-verified dependencies before copying application code,
# so this layer is rebuilt only when requirements.txt changes.
COPY requirements.txt ./
COPY scripts/install_requirements.py ./scripts/
RUN python scripts/install_requirements.py

# Application code and Alembic migration files (no .git, no data/, no .venv/)
COPY alembic.ini ./
COPY migrations/ ./migrations/
COPY llm_metrics/ ./llm_metrics/

# Switch to non-root before the process starts
USER appuser

# Cloud Run sets $PORT (default: 8080 matches Cloud Run's convention).
# The dashboard also reads LLM_METRICS_DATABASE_URL at request time (not here).
ENV PORT=8080

# Two container modes from one image (override CMD at run time):
#
#   Web/API service (default):
#     docker run -e PORT=8080 -e LLM_METRICS_DATABASE_URL=... <image>
#
#   One-shot benchmark job (never the default — requires --real opt-in):
#     docker run -e OPENAI_API_KEY=... -e LLM_METRICS_DATABASE_URL=... <image> \
#         python -m llm_metrics.real_benchmark --provider openai --real \
#         [--workload interactive-chat-v1]
#
# The default entrypoint is the read-only web service: it makes no paid calls.
# --workers 1 and --timeout 120 match single-request Cloud Run concurrency.
CMD exec gunicorn \
    --bind "0.0.0.0:${PORT}" \
    --workers 1 \
    --timeout 120 \
    --worker-class sync \
    "llm_metrics.web:create_app()"
