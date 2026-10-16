// Shared mutable state for the feed and chat views.

export const state = {
  view: 'feed',
  cat: '',
  filter: 'all',     // all / pinned / translated / hands-on
  sort: 'newest',    // newest / important
  tag: '',           // active tag filter (controlled vocab)
  q: '',
  offset: 0,
  limit: 10,
  total: 0,
  items: [],
  selectedId: null,
};
