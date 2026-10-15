// Article feed: list, render, pin, pagination. Deep-dives are read/managed in
// the separate "深度解读" view (dives.js); the feed only triggers / links to them.
import { $, escapeHtml, fmtDate, catBadge, safeExternalUrl } from './util.js';
import { api } from './api.js';
import { state } from './state.js';
import { jumpToDive } from './dives.js';
import { isAuthed, openAuthModal } from './auth.js';

export async function refreshList() {
  renderActiveFilters();
  const params = new URLSearchParams();
  params.set('offset', String(state.offset));
  params.set('limit', String(state.limit));
  if (state.cat) params.set('category', state.cat);
  if (state.q) params.set('q', state.q);
  if (state.filter === 'pinned') params.set('pinned_only', 'true');
  if (state.sort) params.set('sort', state.sort);
  if (state.tag) params.set('tag', state.tag);

  const listEl = $('#article-list');
  listEl.innerHTML = '<div class="muted-card">加载中…</div>';
  try {
    const r = await api('GET', '/api/ai-news/articles?' + params.toString());
    let items = r.items || [];
    if (state.filter === 'translated') {
      items = items.filter(a => a.translation_status === 'ok');
    }
    state.items = items;
    state.total = r.total || 0;
    $('#article-count').textContent = state.total + ' 篇';
    $('#cnt-feed').textContent = state.total;
    renderList();
    renderPageNav();
  } catch (e) {
    listEl.innerHTML = '<div class="muted-card">❌ 加载失败：' + escapeHtml(e.message) + '</div>';
  }
}

const CAT_LABELS = {
  vendor: '官方', expert: '专家', 'x-ai': '大V', community: '社区',
  media: '媒体', paper: '论文', trending: '风向',
};

function renderActiveFilters() {
  const el = $('#active-filters');
  if (!el) return;
  const filters = [];
  if (state.cat) filters.push(['cat', `来源：${CAT_LABELS[state.cat] || state.cat}`]);
  if (state.filter === 'pinned') filters.push(['filter', '只看收藏']);
  if (state.filter === 'translated') filters.push(['filter', '只看已翻译']);
  if (state.tag) filters.push(['tag', `标签：${state.tag}`]);

  el.classList.toggle('hidden', filters.length === 0);
  el.innerHTML = filters.map(([kind, label]) =>
    `<button type="button" data-clear-filter="${kind}" title="清除该筛选">${escapeHtml(label)} <span aria-hidden="true">×</span></button>`
  ).join('');

  el.querySelectorAll('[data-clear-filter]').forEach(button => button.addEventListener('click', () => {
    const kind = button.dataset.clearFilter;
    if (kind === 'cat') {
      state.cat = '';
      document.querySelectorAll('#cat-seg button').forEach(x => x.classList.toggle('on', x.dataset.cat === ''));
    }
    if (kind === 'filter') {
      state.filter = 'all';
      document.querySelectorAll('.seg button[data-filter]').forEach(x => x.classList.toggle('on', x.dataset.filter === 'all'));
    }
    if (kind === 'tag') state.tag = '';
    state.offset = 0;
    refreshList();
  }));
}

function articleCardHtml(a) {
  const title = a.title_zh || a.title || '(无标题)';
  const pinClass = a.pinned ? 'is-pinned' : '';
  const preview = (a.summary_zh || a.summary || '').toString()
    .replace(/https?:\/\/\S+/g, '')
    .replace(/^["“''']+|["”''']+$/g, '')
    .replace(/\s+/g, ' ')
    .trim();
  const ddStatus = a.deep_dive_status;
  const ddBtnLabel = ddStatus === 'ok' ? '查看解读'
    : ddStatus === 'generating' ? '⏳ 生成中…'
    : ddStatus === 'failed' ? '重试解读'
    : '深度解读';
  const ddBusy = ddStatus === 'generating' ? 'is-busy' : '';
  const ddActive = ddStatus === 'ok' ? 'is-done' : '';
  const transBadge = a.translation_status === 'failed'
    ? '<span class="chip chip-trans-fail" title="翻译失败，可点下方按钮重试">⚠️ 翻译失败</span>'
    : a.translation_status === 'ok' ? ''
    : '<span class="chip chip-trans-pending" title="排队等待翻译">待翻译</span>';
  const transAction = a.translation_status === 'ok' ? ''
    : a.translation_status === 'failed'
    ? `<button class="btn-card ghost admin-only" data-action="translate">🔄 重新翻译</button>`
    : `<button class="btn-card ghost admin-only" data-action="translate">🌐 立即翻译</button>`;
  const tagsHtml = (a.tags && a.tags.length)
    ? `<div class="article-tags">${a.tags.slice(0, 2).map(t => `<span class="chip chip-tag" data-tag="${escapeHtml(t)}">${escapeHtml(t)}</span>`).join('')}</div>`
    : '';
  // Importance badge: only show for clearly high-value items (>=8) to keep signal.
  const impHtml = (typeof a.importance === 'number' && a.importance >= 8)
    ? `<span class="imp-badge" title="重要性 ${a.importance}/10">🔥 ${a.importance}</span>` : '';
  const safeUrl = safeExternalUrl(a.url);
  const originBtn = safeUrl
    ? `<a class="btn-card primary" href="${escapeHtml(safeUrl)}" target="_blank" rel="noopener">原文 ↗</a>` : '';
  const copyBtn = safeUrl ? `<button class="btn-card ghost" data-action="copy">复制链接</button>` : '';
  return `
    <article class="article-card ${pinClass}" data-aid="${escapeHtml(a.id)}">
      <header class="card-head">
        ${catBadge(a.category)}
        ${impHtml}
        <div class="card-titlewrap">
          <h3 class="card-title">${escapeHtml(title)}</h3>
        </div>
        <button class="pin-btn ${a.pinned ? 'on' : ''}" data-action="pin" title="${a.pinned ? '取消收藏' : '收藏'}">${a.pinned ? '★' : '☆'}</button>
      </header>
      <div class="card-meta">
        <span class="meta-src">${escapeHtml(a.source || '')}</span>
        <span class="sep">·</span>
        <span>${fmtDate(a.date)}</span>
        ${transBadge}
      </div>
      ${preview ? `<div class="card-preview">${escapeHtml(preview)}</div>` : ''}
      ${tagsHtml}
      <div class="card-actions">
        ${originBtn}
        <button class="btn-card ${ddActive ? 'success' : 'accent'} ${ddBusy}" data-action="dive">${ddBtnLabel}</button>
        <details class="card-more">
          <summary>更多</summary>
          <div class="card-more-menu">
            ${copyBtn}
            <button class="btn-card ghost" data-action="ask" title="带这篇上下文问 AI 助手">问 AI</button>
            <button class="btn-card ghost" data-action="srs" title="加入间隔复习库">加入知识卡</button>
            ${transAction}
          </div>
        </details>
      </div>
    </article>`;
}

export function renderList() {
  const listEl = $('#article-list');
  if (!state.items.length) {
    listEl.innerHTML = '<div class="muted-card" style="padding:48px 16px;text-align:center">📭 这一页没有内容</div>';
    return;
  }
  listEl.innerHTML = state.items.map(articleCardHtml).join('');

  // Tag chips → filter the feed by that tag (toggle off if already active).
  listEl.querySelectorAll('[data-tag]').forEach(chip =>
    chip.addEventListener('click', (e) => {
      e.stopPropagation();
      const t = chip.dataset.tag;
      state.tag = state.tag === t ? '' : t;
      state.offset = 0;
      refreshList();
    }));

  listEl.querySelectorAll('.article-card').forEach(el => {
    const aid = el.dataset.aid;
    el.querySelector('[data-action="dive"]')?.addEventListener('click', () => {
      const a = state.items.find(x => x.id === aid);
      const generate = a?.deep_dive_status !== 'ok';
      jumpToDive(aid, { generate });
    });
    el.querySelector('[data-action="pin"]')?.addEventListener('click', () => togglePin(aid));
    el.querySelector('[data-action="ask"]')?.addEventListener('click', () => {
      const a = state.items.find(x => x.id === aid);
      askAboutArticle(a);
    });
    el.querySelector('[data-action="srs"]')?.addEventListener('click', async (e) => {
      const btn = e.currentTarget, orig = btn.textContent; btn.disabled = true; btn.textContent = '⏳ 加入中…';
      try {
        await api('POST', '/api/ai-news/review/cards', { source_type: 'article', source_id: aid });
        btn.textContent = '✓ 已加入'; btn.classList.add('success');
      } catch (err) {
        btn.textContent = err.status === 409 ? '✓ 已在库' : '❌ 失败';
        if (err.status !== 409) alert('加入复习失败：' + err.message);
        setTimeout(() => { btn.disabled = false; btn.textContent = orig; btn.classList.remove('success'); }, 1600);
      }
    });
    el.querySelector('[data-action="copy"]')?.addEventListener('click', (e) => {
      e.preventDefault();
      const a = state.items.find(x => x.id === aid);
      if (a?.url) {
        navigator.clipboard.writeText(a.url).then(() => {
          const btn = e.currentTarget, orig = btn.textContent;
          btn.textContent = '✓ 已复制'; btn.classList.add('flash');
          setTimeout(() => { btn.textContent = orig; btn.classList.remove('flash'); }, 1400);
        });
      }
    });
    el.querySelector('[data-action="translate"]')?.addEventListener('click', async (e) => {
      const btn = e.currentTarget; const orig = btn.textContent; btn.disabled = true; btn.textContent = '🌐 翻译中…';
      try {
        await api('POST', `/api/ai-news/articles/${aid}/retranslate`);
        await refreshList();
      } catch (err) {
        alert('翻译失败：' + err.message);
        btn.disabled = false; btn.textContent = orig;
      }
    });
  });
}

// Open the chat agent pre-loaded with this article's context, so the user can
// ask about the specific piece without retyping what it is. (Scene-embedded
// agent — same mechanism the reflection "展开聊" uses.)
function askAboutArticle(a) {
  if (!a) return;
  if (!isAuthed()) { openAuthModal('登录后即可用 AI 助手就这篇提问'); return; }
  const chat = window.__sparrowChat;
  if (!chat) { alert('AI 助手未就绪'); return; }
  const title = a.title_zh || a.title || '(无标题)';
  const prompt = `关于这篇文章：《${title}》${a.url ? '（' + a.url + '）' : ''}\n我想了解：`;
  chat.toggle(true);
  chat.input.value = prompt;
  chat.input.focus();
  // Move caret to end so the user just continues typing their question.
  const len = chat.input.value.length;
  try { chat.input.setSelectionRange(len, len); } catch (e) { /* ignore */ }
}

export function renderPageNav() {
  const start = state.total === 0 ? 0 : state.offset + 1;
  const end = Math.min(state.offset + state.limit, state.total);
  $('#page-info').textContent = state.total ? `${start}–${end} / ${state.total}` : '0 / 0';
  $('#btn-prev').disabled = state.offset <= 0;
  $('#btn-next').disabled = state.offset + state.limit >= state.total;
}

export async function togglePin(aid) {
  try {
    const r = await api('POST', `/api/ai-news/articles/${aid}/pin`);
    const a = state.items.find(x => x.id === aid);
    if (a) a.pinned = r.pinned;
    renderList();
  } catch (e) { alert('收藏失败：' + e.message); }
}
