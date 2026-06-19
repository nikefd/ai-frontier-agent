// Shared mutable state for the feed and chat views.

export const state = {
  view: 'feed',
  cat: '',
  filter: 'all',     // all / pinned / translated
  q: '',
  offset: 0,
  limit: 20,
  total: 0,
  items: [],
  selectedId: null,
};
