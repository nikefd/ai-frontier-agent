"""Dates come from the timeline's explicit year boundaries, never today's year."""
import httpx
import pytest

from app.xai_release_notes import parse_xai_release_notes
from app.workers.ai_news_fetcher import _fetch_feed

URL = "https://docs.x.ai/developers/release-notes"
PAGE = b'''<main><h2>October</h2><div class="grid">
  <div>October 14</div><div><span><h3 id="voice-3">Grok Voice 3.0 is available</h3></span>
  <p>The voice model is available.</p></div></div>
  <h2>July</h2><div class="grid"><div>July 8</div><div><h3 id="grok-45">Grok 4.5</h3></div></div>
  <h2>December 2025</h2><div class="grid"><div>Dec 16</div><div><h3 id="voice-api">Voice API</h3></div></div></main>'''


def test_timeline_infers_rollover_from_explicit_year_and_keeps_real_anchors():
    items = parse_xai_release_notes(PAGE, URL)
    assert [item["date"] for item in items] == ["2026-10-14T00:00:00+00:00", "2026-07-08T00:00:00+00:00", "2025-12-16T00:00:00+00:00"]
    assert items[0]["url"] == URL + "#voice-3"
    assert items[0]["summary"] == "The voice model is available."


def test_missing_year_boundary_and_invalid_calendar_dates_are_rejected():
    assert parse_xai_release_notes(PAGE.split(b'<h2>December')[0] + b'</main>', URL) == []
    items = parse_xai_release_notes(PAGE.replace(b'October 14', b'October 99'), URL)
    assert len(items) == 2
    assert parse_xai_release_notes(b'<html>Blocked</html>', URL) == []


@pytest.mark.asyncio
async def test_registered_xai_source_routes_through_dated_adapter():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=PAGE))) as client:
        items, title, error = await _fetch_feed(client, URL)
    assert error is None and title == "xAI API Release Notes"
    assert len(items) == 3
