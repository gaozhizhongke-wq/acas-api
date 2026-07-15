# ACAS v2 - Production Dockerfile
# NOTE: Uses psycopg[binary] (sync), NOT asyncpg. asyncpg has Windows ProactorEventLoop
#       compatibility issues on Windows hosts.
# NOTE: torch / transformers / prophet are intentionally NOT in requirements.txt.
#       They are imported lazily inside the ML engines and degrade gracefully when
#       absent, so the API starts and serves all core endpoints without them.
# NOTE: Uses Tsinghua mirrors (apt + pip) for faster builds on CN networks.

# ─── Builder stage ────────────────────────────────────────────────────────────
FROM python:3.11-slim as builder

# Use Tsinghua Debian mirror for faster apt on CN networks.
RUN sed -i 's|http://deb.debian.org/debian|https://mirrors.tuna.tsinghua.edu.cn/debian|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true

# psycopg[binary] ships its own libpq, so no gcc/libpq-dev toolchain is required.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
# All listed deps have manylinux wheels for cp311 → no source compilation.
# Tsinghua PyPI mirror for fast download.
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
    -r requirements.txt

# ─── Production stage ─────────────────────────────────────────────────────────
FROM python:3.11-slim

# Runtime shared lib for psycopg binary driver + curl for healthcheck.
RUN sed -i 's|http://deb.debian.org/debian|https://mirrors.tuna.tsinghua.edu.cn/debian|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Create non-root user
RUN useradd -m -u 1000 acas

WORKDIR /app

# Create app dir owned by acas (WORKDIR above creates as root; fix ownership here)
RUN mkdir -p /app && chown acas:acas /app

# Copy application (owner = acas for non-root)
COPY --chown=acas:acas run.py ./
COPY --chown=acas:acas src/ ./src/
COPY --chown=acas:acas alembic/ ./alembic/
COPY --chown=acas:acas alembic.ini ./.env.example ./

# Copy deploy/ (observability configs) if present
COPY --chown=acas:acas deploy/ ./deploy/

# Ensure /app is writable by acas (covers subdirs created by COPY)
RUN chown -R acas:acas /app

# Switch to non-root
USER acas

# ─── Health check ─────────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# ─── Run ──────────────────────────────────────────────────────────────────────
# run.py sets WindowsSelectorEventLoop on Windows and runs uvicorn.
# In Docker (Linux) the default selector policy is used.
CMD ["python", "run.py"]
