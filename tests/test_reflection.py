"""Tests for reflection signal time-windowing and tolerant LLM-JSON parsing."""
from app.routers.reflection import _parse_llm_json


def test_parse_clean_json():
    raw = '{"recap": "本周关注 **Agent**", "questions": ["q1", "q2", "q3"]}'
    recap, qs = _parse_llm_json(raw)
    assert "Agent" in recap
    assert qs == ["q1", "q2", "q3"]


def test_parse_json_with_code_fence():
    raw = '```json\n{"recap": "r", "questions": ["a", "b"]}\n```'
    recap, qs = _parse_llm_json(raw)
    assert recap == "r"
    assert qs == ["a", "b"]


def test_parse_garbage_falls_back():
    recap, qs = _parse_llm_json("not json at all")
    assert len(qs) >= 1            # always yields at least one question
    assert isinstance(recap, str)


def test_parse_empty_questions_falls_back():
    raw = '{"recap": "r", "questions": []}'
    recap, qs = _parse_llm_json(raw)
    assert len(qs) >= 1            # empty list → fallback question


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
