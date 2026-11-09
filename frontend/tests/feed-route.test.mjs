import test from 'node:test';
import assert from 'node:assert/strict';
import { readFeedRoute, writeFeedRoute } from '../src/feed-route.js';

test('shared feed URLs restore search, filters and page while preserving language', () => {
  const state = { q: 'Gemini & API 中文', cat: 'vendor', filter: 'hands-on', sort: 'important', tag: 'api', offset: 20 };
  const url = writeFeedRoute('?lang=en&campaign=dev', state);
  assert.deepEqual(readFeedRoute(url), state);
  assert.equal(new URLSearchParams(url).get('lang'), 'en');
  assert.equal(new URLSearchParams(url).get('campaign'), 'dev');
});
test('invalid shared filters and offsets fall back to a usable first page', () => {
  for (const offset of ['-10', 'Infinity', '1.5', 'oops', '9007199254740992']) {
    assert.deepEqual(readFeedRoute(`?cat=invalid&filter=admin&sort=bad&offset=${offset}`), readFeedRoute(''));
  }
});
test('clearing filters removes stale URL values and retains unrelated parameters', () => {
  assert.equal(writeFeedRoute('?lang=zh&q=old&cat=paper&offset=10', readFeedRoute('')), '?lang=zh');
});
