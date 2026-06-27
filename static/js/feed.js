// Article feed: list, render, pin, pagination. Deep-dives are read/managed in
// the separate "深度解读" view (dives.js); the feed only triggers / links to them.
import { $, escapeHtml, fmtDate, catBadge } from './util.js';
import { api } from './api.js';
import { state } from './state.js';
import { jumpToDive } from './dives.js';

export async function refreshList() {
  const params = new URLSearchParams();
  params.set('offset', String(state.offset));
  params.set('limit', String(state.limit));
  if (state.cat) params.set('category', state.cat);
  if (state.q) params.set('q', state.q);
  if (state.filter === 'pinned') params.set('pinned_only', 'true');

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

function articleCardHtml(a) {
  const title = a.title_zh || a.title || '(无标题)';
  const enTitle = a.title_zh && a.title ? a.title : '';
  const pinClass = a.pinned ? 'is-pinned' : '';
  const preview = (a.summary_zh || a.summary || '').toString()
    .replace(/https?:\/\/\S+/g, '')
    .replace(/^["“''']+|["”''']+$/g, '')
    .replace(/\s+/g, ' ')
    .trim();
  const ddStatus = a.deep_dive_status;
  const ddBtnLabel = ddStatus === 'ok' ? '🧠 查看解读 →'
    : ddStatus === 'generating' ? '⏳ 生成中…'
    : ddStatus === 'failed' ? '⚠️ 重试解读'
    : '🧠 深度解读';
  const ddBusy = ddStatus === 'generating' ? 'is-busy' : '';
  const ddActive = ddStatus === 'ok' ? 'is-done' : '';
  const transBadge = a.translation_status === 'ok'
    ? '<span class="chip chip-trans" title="已翻译">🌐 已翻译</span>' : '';
  const transAction = a.translation_status === 'ok' ? ''
    : `<button class="btn-card ghost" data-action="translate">🌐 翻译这篇</button>`;
  const tagsHtml = (a.tags && a.tags.length)
    ? `<div class="article-tags">${a.tags.slice(0, 5).map(t => `<span class="chip chip-tag">${escapeHtml(t)}</span>`).join('')}</div>`
    : '';
  const urlHost = a.url ? (() => { try { return new URL(a.url).hostname.replace(/^www\./, ''); } catch (e) { return ''; } })() : '';
  const originBtn = a.url
    ? `<a class="btn-card primary" href="${escapeHtml(a.url)}" target="_blank" rel="noopener">🔗 阅读原文 ↗</a>` : '';
  const copyBtn = a.url ? `<button class="btn-card ghost" data-action="copy">📋 复制链接</button>` : '';
  return `
    <article class="article-card ${pinClass}" data-aid="${escapeHtml(a.id)}">
      <header class="card-head">
        ${catBadge(a.category)}
        <div class="card-titlewrap">
          <h3 class="card-title">${escapeHtml(title)}</h3>
          ${enTitle ? `<div class="card-en">${escapeHtml(enTitle)}</div>` : ''}
        </div>
        <button class="pin-btn ${a.pinned ? 'on' : ''}" data-action="pin" title="${a.pinned ? '取消收藏' : '收藏'}">${a.pinned ? '★' : '☆'}</button>
      </header>
      <div class="card-meta">
        <span class="meta-src">${escapeHtml(a.source || '')}</span>
        <span class="sep">·</span>
        <span>${fmtDate(a.date)}</span>
        ${urlHost ? `<span class="sep">·</span><span class="meta-host">${escapeHtml(urlHost)}</span>` : ''}
        ${transBadge}
      </div>
      ${preview ? `<div class="card-preview">${escapeHtml(preview)}</div>` : ''}
      ${tagsHtml}
      <div class="card-actions">
        ${originBtn}
        ${copyBtn}
        ${transAction}
        <button class="btn-card ${ddActive ? 'success' : 'accent'} ${ddBusy}" data-action="dive">${ddBtnLabel}</button>
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

  listEl.querySelectorAll('.article-card').forEach(el => {
    const aid = el.dataset.aid;
    el.querySelector('[data-action="dive"]')?.addEventListener('click', () => {
      const a = state.items.find(x => x.id === aid);
      const generate = a?.deep_dive_status !== 'ok';
      jumpToDive(aid, { generate });
    });
    el.querySelector('[data-action="pin"]')?.addEventListener('click', () => togglePin(aid));
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
      const btn = e.currentTarget; btn.disabled = true; btn.textContent = '🌐 翻译中…';
      try {
        await api('POST', `/api/ai-news/articles/${aid}/retranslate`);
        await refreshList();
      } catch (err) {
        alert('翻译失败：' + err.message);
        btn.disabled = false; btn.textContent = '🌐 翻译这篇';
      }
    });
  });
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
