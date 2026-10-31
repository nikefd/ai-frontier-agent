"""Run from repository root: python -m scripts.production_audit --help."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from pydantic import TypeAdapter

from app.production_audit import IndependentEvent, collect_audit
from app.storage import write_json_atomic


async def main() -> int:
    parser = argparse.ArgumentParser(description="只读生产验收与独立官方样本核对（不修改线上数据）")
    parser.add_argument("base_url")
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    parts = urlsplit(args.base_url)
    if parts.scheme not in {"http", "https"} or not parts.netloc or parts.username or parts.password or parts.query or parts.fragment or parts.path not in {"", "/"}:
        parser.error("base_url 必须是无凭证、无路径的 http(s) 站点地址")
    events = TypeAdapter(list[IndependentEvent]).validate_json(args.samples.read_text())
    urls = [str(event.source_url) for event in events]
    if not events or len(urls) != len(set(urls)):
        parser.error("独立样本不能为空或包含重复 URL")
    async with httpx.AsyncClient(base_url=args.base_url.rstrip("/"), timeout=30, headers={
        "User-Agent": "Mozilla/5.0 AIFrontierAudit/1.0",
    }) as client:
        result = await collect_audit(client, events)
    write_json_atomic(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
