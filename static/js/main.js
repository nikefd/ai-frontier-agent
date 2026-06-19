// App entry: view switching and all event wiring.
import { $, $$ } from './util.js';
import { api } from './api.js';
import { state } from './state.js';
import { refreshList } from './feed.js';
import { loadSummary, regenSummary, loadGuides, genGuide, loadSources } from './views.js';
import { initChat, chatSend, startNewConversation, loadConversationMessages } from './chat.js';
import { chat } from './state.js';

if (window.mermaid) {
  window.mermaid.initialize({ startOnLoad: false, theme: 'default', securityLevel: 'loose' });
}

function switchView(v) {
  state.view = v;
  $$('.side-nav button[data-view]').forEach(b => b.classList.toggle('on', b.dataset.view === v));
  $$('.view-pane').forEach(p => p.classList.toggle('hidden', p.id !== 'view-' + v));
  if (v === 'feed') refreshList();
  if (v === 'summary') loadSummary();
  if (v === 'guides') loadGuides();
  if (v === 'sources') loadSources();
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
$('#btn-gen-guide').addEventListener('click', genGuide);

// ── Chat (floating dock) ─────────────────────────────────────────────
let chatOpened = false;
function toggleChatDock(force) {
  const dock = $('#chat-dock'), fab = $('#chat-fab');
  const open = force !== undefined ? force : dock.classList.contains('hidden');
  dock.classList.toggle('hidden', !open);
  fab.classList.toggle('active', open);
  if (open && !chatOpened) { initChat(); chatOpened = true; }
}
$('#chat-fab').addEventListener('click', () => toggleChatDock());
$('#btn-chat-close').addEventListener('click', () => toggleChatDock(false));
$('#btn-chat-send').addEventListener('click', chatSend);
$('#chat-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') chatSend(); });
$('#btn-conv-new').addEventListener('click', startNewConversation);
$('#conv-select').addEventListener('change', (e) => {
  const id = e.target.value;
  if (!id) return;
  chat.convId = id;
  localStorage.setItem('aif_conv_id', id);
  loadConversationMessages(id);
});

// ── Boot ─────────────────────────────────────────────────────────────
refreshList();
