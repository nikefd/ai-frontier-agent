"""Tests for enrichment cleaning helpers (importance clamp + tag whitelist)."""
from app.workers.ai_news_translator import _clean_importance, _clean_tags, TAG_VOCAB, _parse_response


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


def test_parse_enrich_response():
    raw = '[{"id":"a1","title_zh":"标题","summary_zh":"摘要","importance":8,"tags":["发布"]}]'
    out = _parse_response(raw)
    assert out[0]["importance"] == 8 and out[0]["tags"] == ["发布"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
