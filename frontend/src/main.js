// App entry: view switching and all event wiring.
import { $, $$ } from './util.js';
import { api } from './api.js';
import { state } from './state.js';
import { refreshList } from './feed.js';
import { regenSummary, regenProfile } from './views.js';
import { regenReflection } from './reflection.js';
import { generateLearning } from './learning.js';
import { manualNewDive } from './dives.js';
import { addManualCard } from './review.js';
import { switchView } from './nav.js';
import { initAuth } from './auth.js';
// Chat is provided by the bundled sparrow-chat.js component (mounted in index.html).

if (window.mermaid) {
  window.mermaid.initialize({ startOnLoad: false, theme: 'default', securityLevel: 'loose' });
}

// ── Landing / home ───────────────────────────────────────────────────
// The bilingual hero shows on first load; entering reveals the app shell.
function enterStation() {
  document.body.classList.remove('landing-active');
  switchView('feed');
}
$('#btn-enter').addEventListener('click', enterStation);

// ── Nav + filters ────────────────────────────────────────────────────
$('#brand').addEventListener('click', () => {
  document.body.classList.add('landing-active');
  state.cat = ''; state.filter = 'all'; state.q = ''; state.offset = 0;
  const search = $('#search'); if (search) search.value = '';
  $$('#cat-seg button').forEach(x => x.classList.toggle('on', x.dataset.cat === ''));
  $$('.seg button[data-filter]').forEach(x => x.classList.toggle('on', x.dataset.filter === 'all'));
  switchView('feed');
});

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
$('#btn-regen-profile').addEventListener('click', regenProfile);
$('#btn-regen-reflection').addEventListener('click', regenReflection);
$('#btn-gen-path').addEventListener('click', generateLearning);
$('#btn-new-dive').addEventListener('click', manualNewDive);
$('#btn-new-card').addEventListener('click', addManualCard);
$('#btn-toggle-newcard').addEventListener('click', () => {
  const form = $('#srs-new-form');
  form.classList.toggle('hidden');
  if (!form.classList.contains('hidden')) $('#srs-new-front').focus();
});

// ── Boot ─────────────────────────────────────────────────────────────
initAuth();
// Re-load views when the logged-in identity changes (login / logout).
window.addEventListener('aif:auth-changed', () => { state.offset = 0; refreshList(); });
refreshList();
