"""Tests for learning-path JSON parsing and reference resolution."""
from app.routers.learning import _parse_stages, _resolve_reads


def test_parse_stages_clean():
    raw = '{"stages": [{"title": "s1", "goal": "g", "learn": ["a"]}]}'
    assert len(_parse_stages(raw)) == 1


def test_parse_stages_code_fence():
    raw = '```json\n{"stages": [{"title": "s1"}]}\n```'
    assert len(_parse_stages(raw)) == 1


def test_parse_stages_garbage():
    assert _parse_stages("not json") == []


def test_resolve_drops_fabricated_refs():
    # The LLM may hallucinate ids; only refs present in lookup survive.
    lookup = {"dive:a1": {"type": "deep-dive", "id": "a1", "title": "Real", "url": "u"}}
    stages = [{
        "title": "s1", "goal": "g", "learn": ["x"],
        "read": [{"ref": "dive:a1", "note": "real"},
                 {"ref": "dive:FAKE", "note": "hallucinated"}],
        "suggest": "", "practice": "",
    }]
    out = _resolve_reads(stages, lookup)
    assert len(out[0]["read"]) == 1                  # fabricated ref dropped
    assert out[0]["read"][0]["id"] == "a1"
    assert out[0]["read"][0]["note"] == "real"


def test_resolve_normalizes_missing_fields():
    out = _resolve_reads([{"title": "s"}], {})
    assert out[0]["learn"] == [] and out[0]["read"] == []
    assert out[0]["goal"] == "" and out[0]["suggest"] == ""


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
