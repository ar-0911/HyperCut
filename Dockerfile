# One image for the whole app. docker-compose.yml runs it twice: the job server (api) and the web app (web).
# See docs/decisions/0015-docker-compose-for-local-use.md.
FROM ubuntu:24.04

# Node 22 from the official image; Python 3.12, FFmpeg and the system libraries from Ubuntu.
COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22-bookworm-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl ffmpeg python3 python3-venv \
        # MediaPipe (face tracking, speaker cut-out)
        libegl1 libgles2 libgl1 libglib2.0-0t64 \
        # Chrome Headless Shell (Remotion rendering)
        libnss3 libdbus-1-3 libatk1.0-0t64 libatk-bridge2.0-0t64 libgbm1 libasound2t64 libxrandr2 libxkbcommon0 \
        libxfixes3 libxcomposite1 libxdamage1 libpango-1.0-0 libcairo2 libcups2t64 \
    && rm -rf /var/lib/apt/lists/*

# Claude Code, for HYPERCUT_LLM=cli (the user's Claude subscription).
RUN npm install -g @anthropic-ai/claude-code && npm cache clean --force

WORKDIR /app
RUN python3 -m venv /opt/venv && chown -R ubuntu:ubuntu /app /opt/venv
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    HYPERCUT_MEDIA=/app/media
USER ubuntu

# Python pipeline and job server, with every optional backend so a .env switch is all it takes.
COPY --chown=ubuntu:ubuntu pyproject.toml ./
COPY --chown=ubuntu:ubuntu hypercut/ hypercut/
RUN pip install --no-cache-dir -e '.[api,whisper,deepgram,reframe,matte,anthropic,generate]'

# Renderer, plus the headless Chrome it drives (downloaded now, not on the first render).
COPY --chown=ubuntu:ubuntu render/package.json render/package-lock.json render/
RUN cd render && npm ci && npx remotion browser ensure && npm cache clean --force

# Web app. The browser calls the API at this URL, so it is baked in at build time.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_TELEMETRY_DISABLED=1
COPY --chown=ubuntu:ubuntu web/package.json web/package-lock.json web/
RUN cd web && npm ci && npm cache clean --force

COPY --chown=ubuntu:ubuntu . .
RUN cd web && NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL npm run build \
    && mkdir -p /app/media /home/ubuntu/.cache

EXPOSE 8000 3000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
