"""Tests for enrichment cleaning helpers."""
import json

import pytest

import app.workers.ai_news_translator as translator
from app.storage import read_json, write_json_atomic
from app.workers.ai_news_translator import (
    TAG_VOCAB,
    _clean_event_key,
    _clean_hands_on,
    _clean_importance,
    _clean_tags,
    _parse_response,
    _pick_pending,
)


def test_importance_clamped():
    assert _clean_importance(7) == 7
    assert _clean_importance(99) == 10        # clamp high
    assert _clean_importance(-5) == 0         # clamp low
    assert _clean_importance("8") == 8        # string coerced
    assert _clean_importance("nope") is None  # garbage → None
    assert _clean_importance(None) is None


def test_tags_whitelist_only():
    # Only vocab tags survive; invented ones dropped; capped at 3.
    good = TAG_VOCAB[0]
    out = _clean_tags([good, "瞎编的标签", TAG_VOCAB[1], TAG_VOCAB[2], TAG_VOCAB[3]])
    assert "瞎编的标签" not in out
    assert all(t in TAG_VOCAB for t in out)
    assert len(out) <= 3


def test_tags_non_list():
    assert _clean_tags("发布") == []
    assert _clean_tags(None) == []


def test_hands_on_is_single_line_bounded_and_optional():
    assert _clean_hands_on("  先运行最小样例，\n再比较输出。  ") == "先运行最小样例， 再比较输出。"
    assert len(_clean_hands_on("实" * 200)) == 120
    assert _clean_hands_on(None) == ""


def test_event_key_is_normalized_and_rejects_placeholders():
    assert _clean_event_key(" OpenAI / Release / GPT-5 ") == "openai-release-gpt-5"
    assert _clean_event_key("unknown") == ""
    assert _clean_event_key("generic-update") == ""
    assert _clean_event_key(None) == ""


def test_recent_legacy_articles_are_backfilled_once():
    legacy = {
        "id": "old", "title_zh": "标题", "summary_zh": "摘要",
        "translation_status": "ok", "hands_on": None, "event_key": None,
    }
    processed = {**legacy, "id": "done", "hands_on": "", "event_key": ""}
    assert _pick_pending([legacy, processed], 8) == [legacy]


def test_parse_enrich_response():
    raw = '[{"id":"a1","title_zh":"标题","summary_zh":"摘要","importance":8,"tags":["发布"]}]'
    out = _parse_response(raw)
    assert out[0]["importance"] == 8 and out[0]["tags"] == ["发布"]


@pytest.mark.asyncio
async def test_enrichment_persists_actionable_step(tmp_path, monkeypatch):
    articles = [{
        "id": "a1", "title": "Tool release", "summary": "Try a small example",
        "source": "Lab", "translation_status": "pending", "hands_on": None,
    }]
    articles_file = tmp_path / "articles.json"
    write_json_atomic(articles_file, articles)
    monkeypatch.setattr(translator, "ARTICLES_FILE", articles_file)
    monkeypatch.setattr(translator, "_load_articles", lambda: read_json(articles_file, []))
    monkeypatch.setattr(translator, "llm_configured", lambda: True)

    async def fake_chat(*_args, **_kwargs):
        return json.dumps([{
            "id": "a1", "title_zh": "工具发布", "summary_zh": "可运行最小样例。",
            "importance": 7, "tags": ["工具"], "event_key": "lab-release-tool",
            "hands_on": "运行最小样例并记录输出。",
        }], ensure_ascii=False)

    monkeypatch.setattr(translator, "chat_complete", fake_chat)
    assert await translator._translate_once() == 1
    saved = read_json(articles_file, [])[0]
    assert saved["hands_on"] == "运行最小样例并记录输出。"
    assert saved["event_key"] == "lab-release-tool"
    assert saved["translation_status"] == "ok"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
