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
#
# The BuildKit cache mount replaces the old --no-cache-dir: downloaded
# wheels persist on the build host between builds WITHOUT ending up in an
# image layer. --no-cache-dir saved image size but meant every
# requirements.txt edit re-downloaded ~1GB of wheels (torch alone is
# ~200MB) even when only one pin changed. Now that's a local cache hit.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --user \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

# Strip build-only artifacts that ship inside the wheels. None of this is
# reachable at runtime - it's C++ headers for compiling torch extensions,
# torch's own test suite, and google-api-python-client's bundled JSON
# descriptors for ~400 Google Workspace REST APIs (nothing in this repo
# imports googleapiclient at all; it arrives transitively via
# google-generativeai, which talks gRPC to generativelanguage instead).
# Roughly 240MB off the final image for zero functional change.
RUN set -eux; \
    SP=/root/.local/lib/python3.12/site-packages; \
    rm -rf "$SP/torch/include" "$SP/torch/test" \
           "$SP/googleapiclient/discovery_cache/documents"; \
    find "$SP" -name "*.a" -delete

# Pre-download the sentence-transformers model into the image.
# project_manager.py and universal_ingester/utils.py both construct
# SentenceTransformer('all-MiniLM-L6-v2') lazily, which otherwise fetches
# ~90MB from HuggingFace the FIRST time each container touches it - i.e.
# on every `docker compose up` after a recreate, and on every single
# `docker compose run --rm ingest` (fresh container each time, cache gone
# with it). Baking it here turns that into a one-time build cost and makes
# the image work with no outbound network at all.
ENV HF_HOME=/opt/hf-cache
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# ---- client reporter tarball -------------------------------------------
# Built into the image so this backend can hand out its own client package
# over HTTP (GET /live/package). A team that pulls this image then wires a
# test repo with `npm i -D https://<their-host>/live/package/<file>.tgz` -
# no npm account, no registry reachability, and the client version matches
# the server version by construction. See services/config.LIVE_PACKAGE_DIR.
FROM node:24-bookworm-slim AS reporter-builder
WORKDIR /pkg
COPY packages/sentinel-qa-reporter/package.json packages/sentinel-qa-reporter/tsconfig.json ./
# --ignore-scripts: @playwright/test is a build-time type dependency here and
# its postinstall would download browser binaries into a stage that throws
# them away.
RUN npm install --no-audit --no-fund --ignore-scripts
COPY packages/sentinel-qa-reporter/src ./src
COPY packages/sentinel-qa-reporter/README.md packages/sentinel-qa-reporter/LICENSE ./
RUN npm run build && npm pack --pack-destination /out

FROM python:3.12-slim-bookworm AS runtime

RUN groupadd --system appuser && useradd --system --gid appuser --home-dir /app --create-home appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /root/.local /home/appuser/.local
COPY --from=builder --chown=appuser:appuser /opt/hf-cache /opt/hf-cache

# HF_HUB_OFFLINE=1 is safe *because* the model above is baked in: without
# it, sentence-transformers still round-trips to huggingface.co on every
# load just to check for a newer revision, which adds startup latency and
# makes the container fail slowly on a locked-down network. Override it
# (compose `environment:` wins over this) only if you switch to a model
# that isn't in the baked cache.
# HOME must match the COPY destination above, and this is load-bearing, not
# cosmetic. `pip install --user` in the builder wrote to /root/.local, and
# Python resolves user site-packages at startup from $HOME - not from PATH.
# The `useradd --home-dir /app` above makes HOME=/app by default, so the
# interpreter looks in /app/.local, finds nothing, and every import of a
# third-party package fails with ModuleNotFoundError even though the files
# are sitting right there in /home/appuser/.local. Setting HOME explicitly
# is what puts them back on sys.path.
ENV HOME=/home/appuser \
    PATH=/home/appuser/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    HF_HOME=/opt/hf-cache \
    HF_HUB_OFFLINE=1 \
    WEB_CONCURRENCY=1

# Everything above this line is expensive and changes only when
# requirements.txt does. Everything below is a few hundred KB of app code
# that changes constantly. Keeping that order is what makes a rebuild
# after a Python edit take seconds instead of minutes: Docker reuses every
# cached layer up to the first one whose inputs changed, so the 2.2GB
# dependency layer is never rebuilt or re-exported for a code change.
#
# The mkdir/chown deliberately runs BEFORE the code COPYs (and USER
# switches before them too, so `--chown` isn't even needed): a trailing
# `chown -R /app` would have to re-run - and re-write a whole layer -
# every single time any source file changed.
RUN mkdir -p /app/data && chown -R appuser:appuser /app

USER appuser

# App code + the persona/context files it reads at runtime (roles/,
# projects/ are markdown, not secrets - see role_manager.py/project_manager.py).
# universal_ingester is included too so this same image can run ingestion
# on demand (see the `ingest` service in docker-compose.yml) instead of
# needing a second image - its dependencies (pandas/openpyxl/PyPDF2/Pillow/
# pymysql/sqlalchemy) are already in requirements.txt either way.
# Deliberately NOT copied: .env, config.json/config2.json (per-run ingestion
# config, bind-mounted instead - see docker-compose.yml's `ingest` service),
# auth_seed_users.json, users.db, data/ - all runtime state/secrets per
# .gitignore, supplied via env_file and volumes, never baked into the image.
COPY --from=reporter-builder --chown=appuser:appuser /out /app/packages/dist-pack
COPY --chown=appuser:appuser services ./services
COPY --chown=appuser:appuser roles ./roles
COPY --chown=appuser:appuser projects ./projects
COPY --chown=appuser:appuser universal_ingester ./universal_ingester

EXPOSE 8000

# Plain-Python healthcheck instead of curl/wget, so the final image doesn't
# need an extra apt-get layer just to answer its own healthcheck.
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=3).status == 200 else 1)"

# WEB_CONCURRENCY defaults to 1 worker - conservative, not required anymore.
# state.py's current_ingestion_id/lance_db/duck_conn used to be mutable
# globals swapped per-request by ensure_ingestion_loaded(), which was NOT
# safe for two concurrent requests against different ingestions landing on
# the same worker's event loop (one could start querying the other's
# ingestion mid-await). That's fixed: they're now contextvars, isolated per
# request/asyncio Task (see state.py), so it's safe to raise this for more
# throughput. The remaining caveat at any worker count: two requests for the
# SAME ingestion, on the SAME worker, running truly concurrently (the
# threadpool cold-load path allows this) share one DuckDB connection object
# from the warm pool - DuckDB connections aren't guaranteed safe for
# concurrent use from multiple threads without per-thread cursor()s, which
# this codebase doesn't yet do.
#
# `exec` is load-bearing, not style. Without it `sh` stays PID 1 with uvicorn
# as its child, and sh does not forward signals - so `docker stop` / `docker
# compose restart` SIGTERMs sh, uvicorn never hears about it, and 10s later
# the whole container is SIGKILLed. That skips FastAPI's lifespan shutdown
# entirely: in-flight requests are cut off, the DuckDB connection is never
# closed, and the auto-ingest watcher never releases its lock. With `exec`,
# uvicorn replaces sh as PID 1 and receives SIGTERM directly.
CMD ["sh", "-c", "exec uvicorn services.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY}"]
