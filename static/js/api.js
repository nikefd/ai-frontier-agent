// HTTP + rendering helpers shared across views.

// Global handler invoked whenever a request returns 401 (set by auth.js so the
// login modal pops up). Kept here so every api() caller funnels through it.
let unauthorizedHandler = null;
export function setUnauthorizedHandler(fn) { unauthorizedHandler = fn; }

export async function api(method, path, body) {
  const opts = { method, headers: { 'content-type': 'application/json' } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch(path, opts);
  const txt = await r.text();
  let json;
  try { json = JSON.parse(txt); } catch (e) { json = { _raw: txt }; }
  if (!r.ok) {
    if (r.status === 401 && unauthorizedHandler) {
      try { unauthorizedHandler(); } catch (e) { /* ignore */ }
    }
    const err = new Error(json.detail || json.error || ('HTTP ' + r.status));
    err.status = r.status;
    throw err;
  }
  return json;
}

// Convert ```mermaid fences inside a rendered markdown block into diagrams.
export async function renderMermaidInside(rootEl) {
  if (!rootEl || !window.mermaid) return;
  rootEl.querySelectorAll('pre > code.language-mermaid').forEach(code => {
    try {
      const wrap = document.createElement('div');
      wrap.className = 'mermaid';
      wrap.textContent = code.textContent;
      code.parentElement.replaceWith(wrap);
    } catch (e) { /* swallow */ }
  });
  try {
    await window.mermaid.run({
      querySelector: rootEl.tagName.toLowerCase() + ' .mermaid',
      suppressErrors: true,
    });
  } catch (e) { /* ignore */ }
}
