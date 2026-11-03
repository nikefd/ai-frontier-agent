"""Regression coverage for the devsite → AI Studio Markdown migration."""
import httpx
import pytest

from app.workers.ai_news_fetcher import _fetch_feed, _parse_gemini_changelog_entries

OLD = "https://ai.google.dev/gemini-api/docs/changelog"
NEW = "https://aistudio.google.com/docs/changelog"
PAGE = b'''# Release notes
## November 2, 2026  {% id="11-02-2026" %}
* **Model retirement**: Review
  [migration](/docs/deprecations#model).

  API requests change next month.
  * Nested detail, not a separate release.
* **New tool**: Released [tool](/docs/tools).
## October 30, 2026 {% id="10-30-2026" %}
* **Documentation update**: No separate landing page.
'''


def test_markdown_preserves_dates_siblings_nested_details_and_real_links():
    entries = _parse_gemini_changelog_entries(PAGE, NEW)
    assert [x['title'] for x in entries] == ['Model retirement', 'New tool', 'Documentation update']
    assert entries[0]['url'] == 'https://aistudio.google.com/docs/deprecations#model'
    assert entries[0]['date'] == '2026-11-02T00:00:00+00:00'
    assert 'Nested detail' in entries[0]['summary']
    assert entries[2]['url'] == NEW + '#10-30-2026'
    assert entries[2]['date'].startswith('2026-10-30')


@pytest.mark.parametrize('page', [b'# Sign in\n* Log in', b'## November 99, 2026\n* **Bad date**: Nope', b'## Help\n* **Undated**: Nope'])
def test_missing_or_invalid_publication_dates_fail_closed(page):
    assert _parse_gemini_changelog_entries(page, NEW) == []


def test_unknown_section_does_not_inherit_previous_date_and_entries_are_bounded():
    page = PAGE + b'## Help\n* **Not a release**: Ignore me.\n'
    assert len(_parse_gemini_changelog_entries(page, NEW)) == 3
    page = b'## November 2, 2026\n' + b''.join(
        f'* **Item {i}**: [docs](/docs/item-{i}).\n'.encode() for i in range(25)
    )
    assert len(_parse_gemini_changelog_entries(page, NEW)) == 20


@pytest.mark.asyncio
async def test_fetch_uses_redirect_destination_for_markdown_links():
    def handler(request):
        assert request.headers["accept"].startswith("text/markdown")
        if str(request.url) == OLD:
            return httpx.Response(301, headers={'location': NEW})
        assert str(request.url) == NEW
        return httpx.Response(200, content=PAGE, headers={'content-type': 'text/plain'})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        entries, source, error = await _fetch_feed(client, OLD)
    assert error is None
    assert source == 'Gemini API Release Notes'
    assert entries[0]['url'].startswith('https://aistudio.google.com/docs/')
