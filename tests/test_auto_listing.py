from __future__ import annotations

from app.auto_listing import parse_auto_listing_entries


def test_auto_listing_keeps_only_same_site_dated_updates() -> None:
    page = b"""<main>
      <article><a href="/tags/models">Models</a><a href="/news/model-x"><h2>Introducing Model X</h2></a>
        <time datetime="2026-10-25T09:30:00Z">October 25, 2026</time>
        <p>First-party model release.</p></article>
      <article><a href="/news/agent"><h2>Agent Platform Update</h2></a>
        <time>2026-10-24</time></article>
      <article><a href="https://tracker.test/story"><h2>External Story</h2></a>
        <time>2026-10-23</time></article>
      <article><a href="/news/undated"><h2>Undated Post</h2></a></article>
    </main>"""

    entries = parse_auto_listing_entries(page, "https://lab.test/news")

    assert [entry["title"] for entry in entries] == [
        "Introducing Model X", "Agent Platform Update",
    ]
    assert entries[0]["date"] == "2026-10-25T09:30:00+00:00"
    assert entries[0]["summary"] == "First-party model release."
    assert all(entry["url"].startswith("https://lab.test/") for entry in entries)
