# 单镜像：FastAPI app + APScheduler 进程内抓取。零 npm 依赖（前端是原生 JS）。
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
COPY static/ static/
COPY seed-data/ seed-data/
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh

ENV AIF_HOST=0.0.0.0 \
    AIF_PORT=9702 \
    AIF_DATA_DIR=/data

EXPOSE 9702

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD curl -fsS http://127.0.0.1:9702/api/health > /dev/null || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9702"]
