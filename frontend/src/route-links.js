export const ROUTE_VIEWS = ['feed', 'foryou', 'summary', 'dives', 'review', 'reflection', 'profile', 'sources', 'admin', 'learning', 'experiments'];
export function clientRoute(href, current, language) {
  const url = new URL(href, current), origin = new URL(current);
  if (url.origin !== origin.origin || url.hash || !ROUTE_VIEWS.includes(url.pathname.slice(1))) return null;
  // Language is initialized at module load; language changes need a document load.
  if ((url.searchParams.get('lang') || language) !== (origin.searchParams.get('lang') || language)) return null;
  return url;
}
export function installRouteLinks(applyRoute) {
  document.addEventListener('click', event => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const anchor = event.target.closest?.('a[href]');
    if (!anchor || anchor.hasAttribute('download') || anchor.target && anchor.target !== '_self') return;
    const next = clientRoute(anchor.href, location.href, document.documentElement.lang.startsWith('zh') ? 'zh' : 'en');
    if (!next) return;
    event.preventDefault();
    if (next.href !== location.href) history.pushState({}, '', next.pathname + next.search);
    applyRoute();
    window.scrollTo({ top: 0, behavior: 'instant' });
  });
}
