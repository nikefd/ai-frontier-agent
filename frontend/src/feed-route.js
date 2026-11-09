// Public reading state only; never serialize account data or credentials.
const categories = ['', 'vendor', 'blog', 'expert', 'x-ai', 'community', 'media', 'paper', 'trending'];
const defaults = { q: '', cat: '', filter: 'all', sort: 'newest', tag: '', offset: 0 };
export function readFeedRoute(search) {
  const params = new URLSearchParams(search);
  const offset = Number(params.get('offset') || 0);
  return {
    q: params.get('q') || '',
    cat: categories.includes(params.get('cat')) ? params.get('cat') : '',
    filter: ['pinned', 'translated', 'hands-on'].includes(params.get('filter')) ? params.get('filter') : 'all',
    sort: params.get('sort') === 'important' ? 'important' : 'newest',
    tag: params.get('tag') || '',
    offset: Number.isSafeInteger(offset) && offset >= 0 ? offset : 0,
  };
}
export function writeFeedRoute(search, state) {
  const params = new URLSearchParams(search);
  for (const [key, fallback] of Object.entries(defaults)) {
    if (state[key] === fallback) params.delete(key);
    else params.set(key, String(state[key]));
  }
  const query = params.toString();
  return query ? '?' + query : '';
}
export function syncFeedControls(state) {
  document.querySelector('#search').value = state.q;
  for (const [selector, key] of [['#cat-seg button', 'cat'], ['.seg button[data-filter]', 'filter'], ['#sort-seg button', 'sort']]) {
    document.querySelectorAll(selector).forEach(button => button.classList.toggle('on', button.dataset[key] === state[key]));
  }
}
