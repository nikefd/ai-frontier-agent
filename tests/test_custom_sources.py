from __future__ import annotations

from app.custom_sources import (
    add_custom_source,
    delete_custom_source,
    load_custom_source_specs,
    set_custom_source_enabled,
)


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
    assert loaded[0]["enabled"] is True

    disabled = set_custom_source_enabled(
        path,
        source["url"],
        enabled=False,
        updated_at="2026-10-25T12:00:00+00:00",
        updated_by="u_admin",
    )
    assert disabled and disabled["enabled"] is False
    assert load_custom_source_specs(path)[0]["enabled"] is False

    removed = delete_custom_source(path, source["url"])
    assert removed and removed["name"] == "Lab Updates"
    assert load_custom_source_specs(path) == []
    assert delete_custom_source(path, source["url"]) is None


def test_custom_source_loader_accepts_only_complete_page_adapters(tmp_path) -> None:
    path = tmp_path / "custom-sources.json"
    assert add_custom_source(path, {
        "url": "https://lab.test/sitemap.xml", "name": "Lab News",
        "kind": "sitemap", "format": "sitemap", "include_paths": ["/news/"],
    }) is True
    assert add_custom_source(path, {
        "url": "https://studio.test/updates", "name": "Studio Updates",
        "kind": "update_page", "format": "auto_listing",
    }) is True
    assert add_custom_source(path, {
        "url": "https://broken.test/sitemap.xml", "name": "Broken Sitemap",
        "kind": "sitemap", "format": "sitemap",
    }) is True

    loaded = load_custom_source_specs(path)
    assert [item["name"] for item in loaded] == ["Lab News", "Studio Updates"]
    assert loaded[0]["include_paths"] == ["/news/"]
