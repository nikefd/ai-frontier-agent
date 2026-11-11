// Runs before first paint. Deep links must not display the landing hero while
// the main module or session is loading. Kept external for the strict CSP.
if (location.pathname.replace(/\/+$/, '')) {
  document.documentElement.classList.add('route-pending');
}
