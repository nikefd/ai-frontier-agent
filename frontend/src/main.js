import { uiText, uiTemplate, initI18n } from './i18n.js';
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
import { switchView, showLanding, applyRoute } from './nav.js';
import { initAuth } from './auth.js';
import { renderMarkdown } from './markdown.js';
// Chat is provided by the bundled classic component and mounted here after the
// safe Markdown renderer is available.

// The classic chat component cannot import ES modules itself. Give it the same
// DOMPurify-backed renderer used by every other LLM content surface.
initI18n();
window.__renderSafeMarkdown = renderMarkdown;
if (window.SparrowChat) {
  window.__sparrowChat = window.SparrowChat.mount({
    endpoint: '/api/agent/chat',
    conversationsApi: '/api/agent/conversations',
    title: uiText('💬 AI 助理'),
    hint: uiText('我能查文章/数据源/追踪主题，并帮你建追踪主题、收藏文章。试试「帮我盯住 RAG 进展」。'),
    accent: '#7c3aed',
    storageKey: 'aif_conv_id',
    i18n: {
      send: uiText('发送'), placeholder: uiText('帮我查查最近的 Agent 进展…'), history: uiText('历史会话'),
      newChat: uiText('新对话'), resize: uiText('放大 / 缩小'), close: uiText('收起'), back: uiText('返回'),
      thinking: uiText('思考中'), emptyNew: uiText('开始一段新对话，或点 🕘 查看历史。'),
      newStarted: uiText('新对话已开始 ✨'), loading: uiText('加载中…'), noConversations: uiText('还没有历史会话。'),
      loadFailed: uiText('加载失败。'), emptyConversation: uiText('这个会话还没有消息。'), sources: uiText('来源'),
      messages: uiText('条'), untitled: uiText('新对话'), del: uiText('删除'), justNow: uiText('刚刚'),
      minAgo: uiText(' 分钟前'), hourAgo: uiText(' 小时前'), dayAgo: uiText(' 天前'),
    },
  });
}

// ── Landing / home ───────────────────────────────────────────────────
// The concise home page offers two useful starting points.
$$('[data-enter-view]').forEach(b =>
  b.addEventListener('click', () => switchView(b.dataset.enterView)));

// ── Nav + filters ────────────────────────────────────────────────────
// Brand (logo) → back to the landing/home page.
$('#brand').addEventListener('click', () => {
  state.cat = ''; state.filter = 'all'; state.q = ''; state.offset = 0;
  const search = $('#search'); if (search) search.value = '';
  $$('#cat-seg button').forEach(x => x.classList.toggle('on', x.dataset.cat === ''));
  $$('.seg button[data-filter]').forEach(x => x.classList.toggle('on', x.dataset.filter === 'all'));
  showLanding();
});

$$('.side-nav button[data-view]').forEach(b =>
  b.addEventListener('click', () => switchView(b.dataset.view)));

// ── Mobile bottom tab bar + "更多" sheet ──────────────────────────────
$$('.bottom-tabs button[data-view]').forEach(b =>
  b.addEventListener('click', () => switchView(b.dataset.view)));

const moreSheet = $('#more-sheet');
$('#tab-more').addEventListener('click', () => moreSheet.classList.remove('hidden'));
$('#more-close').addEventListener('click', () => moreSheet.classList.add('hidden'));
moreSheet.addEventListener('click', (e) => { if (e.target === moreSheet) moreSheet.classList.add('hidden'); });
$$('#more-sheet button[data-view]').forEach(b =>
  b.addEventListener('click', () => { switchView(b.dataset.view); moreSheet.classList.add('hidden'); }));

$$('#cat-seg button').forEach(b => b.addEventListener('click', () => {
  $$('#cat-seg button').forEach(x => x.classList.remove('on'));
  b.classList.add('on');
  state.cat = b.dataset.cat;
  state.offset = 0;
  b.closest('details')?.removeAttribute('open');
  refreshList();
}));

$$('.seg button[data-filter]').forEach(b => b.addEventListener('click', () => {
  $$('.seg button[data-filter]').forEach(x => x.classList.remove('on'));
  b.classList.add('on');
  state.filter = b.dataset.filter;
  state.offset = 0;
  b.closest('details')?.removeAttribute('open');
  refreshList();
}));

$$('#sort-seg button[data-sort]').forEach(b => b.addEventListener('click', () => {
  $$('#sort-seg button[data-sort]').forEach(x => x.classList.remove('on'));
  b.classList.add('on');
  state.sort = b.dataset.sort;
  state.offset = 0;
  refreshList();
}));

$('#search').addEventListener('input', (e) => {
  state.q = e.target.value.trim();
  state.offset = 0;
  clearTimeout(window.__searchTimer);
  window.__searchTimer = setTimeout(refreshList, 250);
});

// Native details keep menus lightweight; add the two expected popover
// behaviours they do not provide by themselves: click-away and Escape.
document.addEventListener('click', (e) => {
  document.querySelectorAll('.filter-menu[open], .card-more[open]').forEach(menu => {
    if (!menu.contains(e.target) || e.target.closest('.card-more-menu button')) menu.open = false;
  });
});
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  document.querySelectorAll('.filter-menu[open], .card-more[open]').forEach(menu => { menu.open = false; });
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
    btn.title = uiTemplate`+${r.added || 0} 篇 · 总计 ${state.total}`;
  } catch (e) { icon.textContent = '↻'; btn.disabled = false; alert(uiText('抓取失败：') + e.message); }
});

$('#btn-translate').addEventListener('click', async () => {
  const btn = $('#btn-translate'); btn.disabled = true; btn.textContent = '⏳';
  try { await api('POST', '/api/ai-news/translate/run'); await refreshList(); }
  catch (e) { alert(uiText('翻译失败：') + e.message); }
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
// Resolve the persisted session before loading a user-scoped deep link. Without
// this ordering, /experiments (and other personal views) briefly decides the
// user is anonymous and never fetches its data after initAuth completes.
async function boot() {
  await initAuth();
  // Re-load the current view when the logged-in identity changes (login / logout).
  window.addEventListener('aif:auth-changed', () => { state.offset = 0; applyRoute(); });
  // Restore the view from the URL (deep-link / refresh / back-forward).
  applyRoute();
}
boot();
