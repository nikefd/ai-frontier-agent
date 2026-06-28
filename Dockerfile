# 多阶段构建：先用 Node 构建前端（Vite → static/dist，带内容指纹），
# 再拷进 Python 运行镜像。

# ── Stage 1: build frontend ──────────────────────────────────────────
FROM node:20-slim AS frontend
# WORKDIR 设成 /build/frontend，使 vite 的 outDir '../static/dist' 落在 /build/static/dist
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
# 产出在 /build/static/dist（vite outDir 为 ../static/dist，相对 /build/frontend）

# ── Stage 2: python runtime ──────────────────────────────────────────
FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
# 先装依赖（利用层缓存）；--no-build-isolation 避免重复解析
RUN pip install --no-cache-dir \
    "fastapi>=0.115" "uvicorn[standard]>=0.30" "httpx>=0.27" \
    "feedparser>=6.0" "beautifulsoup4>=4.12" "apscheduler>=3.10" \
    "pydantic-settings>=2.5" "python-dateutil>=2.9" "lxml>=5.3" \
    "sparrow-agent>=0.2.0" "bcrypt>=4.1" "itsdangerous>=2.2"

COPY app/ app/
COPY agent/ agent/
COPY seed-data/ seed-data/
COPY docker-entrypoint.sh .
# 前端构建产物（指纹化的 JS/CSS + index.html）
COPY --from=frontend /build/static/dist static/dist
RUN chmod +x docker-entrypoint.sh

ENV AIF_HOST=0.0.0.0 \
    AIF_PORT=9702 \
    AIF_DATA_DIR=/data

EXPOSE 9702

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD curl -fsS http://127.0.0.1:9702/api/health > /dev/null || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9702"]
