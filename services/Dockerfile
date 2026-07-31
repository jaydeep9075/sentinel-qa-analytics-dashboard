# Build context is the repo root (docker-compose.yml passes `context: .`),
# since the app imports as the `services` package and also needs the
# sibling roles/ and projects/ directories at runtime.
#
# Two-stage build: compilers and build headers (needed by a couple of
# packages without prebuilt wheels for every platform) never reach the
# final image, only the installed site-packages does.

FROM python:3.12-slim-bookworm AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# --extra-index-url pulls the CPU-only build of torch (sentence-transformers'
# real runtime dependency, not optional - see requirements.txt). Without
# this, pip resolves the default PyPI wheel, which for some torch releases
# is a multi-GB CUDA build this service never uses - pure image bloat for a
# GPU that doesn't exist in this container. --user keeps the install under
# a path that's cheap to copy wholesale into the runtime stage below.
RUN pip install --no-cache-dir --user \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

FROM python:3.12-slim-bookworm AS runtime

RUN groupadd --system appuser && useradd --system --gid appuser --home-dir /app --create-home appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /root/.local /home/appuser/.local

ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    WEB_CONCURRENCY=1

# App code + the persona/context files it reads at runtime (roles/,
# projects/ are markdown, not secrets - see role_manager.py/project_manager.py).
# Deliberately NOT copied: .env, config.json (unused by services/ - only the
# separate universal_ingester tool reads it), auth_seed_users.json, users.db,
# data/ - all runtime state/secrets per .gitignore, supplied via env_file and
# volumes in docker-compose.yml, never baked into the image.
COPY services ./services
COPY roles ./roles
COPY projects ./projects

RUN mkdir -p /app/data && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Plain-Python healthcheck instead of curl/wget, so the final image doesn't
# need an extra apt-get layer just to answer its own healthcheck.
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=3).status == 200 else 1)"

# WEB_CONCURRENCY defaults to 1 worker deliberately, not for lack of CPU
# headroom: state.py's current_ingestion_id/lance_db/duck_conn are mutable
# globals swapped per-request by ensure_ingestion_loaded(), not request-scoped.
# That's safe across separate worker *processes* (each has its own globals)
# but NOT safe for two concurrent requests against different ingestions
# landing on the SAME worker's event loop - one can start querying the
# other's ingestion mid-await. Raise this only once that's fixed (e.g. via
# contextvars-scoped ingestion state), or if your usage pattern never has
# concurrent requests against different ingestions.
CMD ["sh", "-c", "uvicorn services.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY}"]
