#!/bin/sh
# 首次启动：若数据卷里没有 ai-news 数据，用镜像内的种子数据初始化。
# 卷已有数据则跳过（保留用户/抓取产生的真实数据）。
set -e

AINEWS_DIR="${AIF_DATA_DIR:-/data}/ai-news"

if [ ! -f "$AINEWS_DIR/articles.json" ]; then
  echo "[entrypoint] 数据卷为空，灌入种子数据 → $AINEWS_DIR"
  mkdir -p "$AINEWS_DIR"
  cp -r /app/seed-data/ai-news/. "$AINEWS_DIR/"
else
  echo "[entrypoint] 数据卷已有 articles.json，跳过种子灌入"
fi

exec "$@"
