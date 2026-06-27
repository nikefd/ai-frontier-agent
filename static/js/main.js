// App entry: view switching and all event wiring.
import { $, $$ } from './util.js';
import { api } from './api.js';
import { state } from './state.js';
import { refreshList } from './feed.js';
import { regenSummary } from './views.js';
import { manualNewDive } from './dives.js';
import { switchView } from './nav.js';
// Chat is provided by the bundled sparrow-chat.js component (mounted in index.html).

if (window.mermaid) {
  window.mermaid.initialize({ startOnLoad: false, theme: 'default', securityLevel: 'loose' });
}

// ── Nav + filters ────────────────────────────────────────────────────
$$('.side-nav button[data-view]').forEach(b =>
  b.addEventListener('click', () => switchView(b.dataset.view)));

$$('#cat-seg button').forEach(b => b.addEventListener('click', () => {
  $$('#cat-seg button').forEach(x => x.classList.remove('on'));
  b.classList.add('on');
  state.cat = b.dataset.cat;
  state.offset = 0;
  refreshList();
}));

$$('.seg button[data-filter]').forEach(b => b.addEventListener('click', () => {
  $$('.seg button[data-filter]').forEach(x => x.classList.remove('on'));
  b.classList.add('on');
  state.filter = b.dataset.filter;
  state.offset = 0;
  refreshList();
}));

$('#search').addEventListener('input', (e) => {
  state.q = e.target.value.trim();
  state.offset = 0;
  clearTimeout(window.__searchTimer);
  window.__searchTimer = setTimeout(refreshList, 250);
});

// ── Pagination ───────────────────────────────────────────────────────
$('#btn-prev').addEventListener('click', () => {
  state.offset = Math.max(0, state.offset - state.limit);
  refreshList();
});
$('#btn-next').addEventListener('click', () => {
  state.offset = state.offset + state.limit;
  refreshList();
});

// ── Toolbar actions ──────────────────────────────────────────────────
$('#btn-fetch').addEventListener('click', async () => {
  const btn = $('#btn-fetch'), icon = $('#fetch-icon');
  btn.disabled = true; icon.textContent = '⏳';
  try {
    const r = await api('POST', '/api/ai-news/fetch');
    state.offset = 0; await refreshList();
    icon.textContent = '↻';
    btn.disabled = false;
    btn.title = `+${r.added || 0} 篇 · 总计 ${state.total}`;
  } catch (e) { icon.textContent = '↻'; btn.disabled = false; alert('抓取失败：' + e.message); }
});

$('#btn-translate').addEventListener('click', async () => {
  const btn = $('#btn-translate'); btn.disabled = true; btn.textContent = '⏳';
  try { await api('POST', '/api/ai-news/translate/run'); await refreshList(); }
  catch (e) { alert('翻译失败：' + e.message); }
  finally { btn.disabled = false; btn.textContent = '🌐'; }
});

$('#btn-regen-summary').addEventListener('click', regenSummary);
$('#btn-new-dive').addEventListener('click', manualNewDive);

// ── Boot ─────────────────────────────────────────────────────────────
refreshList();
