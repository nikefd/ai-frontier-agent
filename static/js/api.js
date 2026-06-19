// HTTP + rendering helpers shared across views.

export async function api(method, path, body) {
  const opts = { method, headers: { 'content-type': 'application/json' } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch(path, opts);
  const txt = await r.text();
  let json;
  try { json = JSON.parse(txt); } catch (e) { json = { _raw: txt }; }
  if (!r.ok) throw new Error(json.detail || json.error || ('HTTP ' + r.status));
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
