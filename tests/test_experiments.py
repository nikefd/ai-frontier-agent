"""Experiment-card parsing and safety boundaries."""
from app.routers.experiments import _allowed_links, _parse_payload, _sanitize_card


ARTICLE = {
    "id": "a1",
    "title": "Tool launch",
    "url": "https://example.com/launch",
    "summary": "Docs: https://docs.example.com/start.",
    "hands_on": "Try the official quickstart",
}


def test_parse_payload_accepts_code_fence():
    assert _parse_payload('```json\n{"title": "x"}\n```')["title"] == "x"


def test_allowed_links_strips_sentence_punctuation():
    assert _allowed_links(ARTICLE) == [
        "https://example.com/launch",
        "https://docs.example.com/start",
    ]


def test_allowed_links_rejects_non_http_source():
    article = {**ARTICLE, "url": "javascript:alert(1)", "summary": ""}
    assert _allowed_links(article) == []
    assert _sanitize_card({"official_links": []}, article)["official_links"] == []


def test_sanitize_drops_fabricated_links_and_keeps_source():
    raw = {
        "title": "实验", "goal": "验证", "duration_minutes": 15,
        "official_links": [
            {"label": "假的", "url": "https://evil.example/fake"},
            {"label": "文档", "url": "https://docs.example.com/start"},
        ],
        "steps": [{"title": "s", "action": "a"}] * 3,
        "success_criteria": ["ok"],
    }
    card = _sanitize_card(raw, ARTICLE)
    assert [x["url"] for x in card["official_links"]] == [
        "https://example.com/launch",
        "https://docs.example.com/start",
    ]


def test_sanitize_bounds_model_output():
    raw = {
        "title": "x", "goal": "g", "duration_minutes": 44, "difficulty": "专家",
        "prerequisites": [str(x) for x in range(10)],
        "steps": [{"title": str(x), "action": "do", "expected": "see"} for x in range(9)],
        "success_criteria": [str(x) for x in range(9)],
        "risks": [str(x) for x in range(9)],
    }
    card = _sanitize_card(raw, ARTICLE)
    assert card["duration_minutes"] == 30
    assert card["difficulty"] == "入门"
    assert len(card["prerequisites"]) == 5
    assert len(card["steps"]) == 5
    assert len(card["success_criteria"]) == 4
    assert len(card["risks"]) == 4


def test_sanitize_requires_action_for_step():
    card = _sanitize_card({"steps": [{"title": "empty"}, {"action": "run"}]}, ARTICLE)
    assert len(card["steps"]) == 1
    assert card["steps"][0]["title"] == "步骤 1"
