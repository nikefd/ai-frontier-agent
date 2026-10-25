from __future__ import annotations

from app.custom_sources import add_custom_source, load_custom_source_specs


def test_custom_sources_are_persisted_normalized_and_deduplicated(tmp_path) -> None:
    path = tmp_path / "custom-sources.json"
    source = {
        "url": "https://lab.test/feed.xml",
        "name": "Lab Updates",
        "kind": "rss",
        "category": "community",
        "cadence": "slow",
    }

    assert add_custom_source(path, source) is True
    assert add_custom_source(path, source) is False

    loaded = load_custom_source_specs(path)
    assert len(loaded) == 1
    assert loaded[0]["category"] == "vendor"
    assert loaded[0]["cadence"] == "fast"
    assert loaded[0]["tier"] == "high"
    assert loaded[0]["custom"] is True
