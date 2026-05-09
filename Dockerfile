# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: Build the React frontend
# ─────────────────────────────────────────────────────────────────────────────
FROM node:22-slim AS frontend-builder
WORKDIR /build

COPY web/frontend/package*.json ./
RUN npm ci --prefer-offline

COPY web/frontend/ ./
RUN npm run build

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: Runtime image
#
# chatwire is an iMessage bridge designed for macOS. Inside Docker the
# iMessage read/send features are unavailable (no chat.db, no AppleScript).
# What DOES work in this image:
#   ✓ Web dashboard + React SPA (served from /app)
#   ✓ REST API (api/v1/*)
#   ✓ SSE live-update stream (tails a mounted mirror.jsonl)
#   ✓ Push-notification subscription endpoint
#   ✓ Healthz probe (/healthz)
#
# What DOES NOT work (macOS only):
#   ✗ Reading chat.db          (requires Full Disk Access on macOS)
#   ✗ Sending iMessages        (requires AppleScript + Messages.app)
#   ✗ macOS menu-bar toolbar   (rumps, PyObjC)
#
# Typical Docker use-cases:
#   - Dashboard-only view on a Linux host that mounts a shared ~/.chatwire/
#     over NFS or sshfs from an mbair running the bridge natively.
#   - CI smoke-tests and integration tests.
#   - Self-hosted demo / dev environments.
#
# Runtime environment variables (all optional):
#   WEB_PORT=8723           Override the listening port.
#   SELF_HANDLES            Comma-separated iMessage handles to treat as self.
#   TG_BOT_TOKEN            Telegram bot token (enables Telegram relay).
#   TG_CHAT_ID              Telegram chat/group ID.
#   WEB_SECRET_KEY          HMAC secret for session cookies.
#
# State / config is read from ~/.chatwire (i.e. /root/.chatwire when running
# as root, the default). Mount a host directory there to persist state or to
# supply a pre-built config.json:
#   docker run -v /path/to/chatwire-state:/root/.chatwire ...
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime
WORKDIR /app

# gcc + libffi-dev are needed to build cffi (pulled in by cryptography).
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python runtime dependencies.
# rumps is macOS-only and is excluded automatically on Linux by the
# `sys_platform == 'darwin'` marker in pyproject.toml, so we install
# the remaining deps directly here.
RUN pip install --no-cache-dir \
        "fastapi>=0.110" \
        "uvicorn[standard]>=0.27" \
        "jinja2>=3.1" \
        "python-multipart>=0.0.9" \
        "pywebpush>=2.0" \
        httpx \
        "jsonschema>=4" \
        "cryptography>=2.6"

# Copy the source tree (node_modules and other large dirs are in .dockerignore).
COPY . .

# Overwrite the (empty) web/frontend/dist/ with the production build from Stage 1.
COPY --from=frontend-builder /build/dist/ web/frontend/dist/

EXPOSE 8723
ENV WEB_PORT=8723

CMD ["python", "web/main.py"]
