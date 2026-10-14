// Deep-dive library: an independent reading area decoupled from the feed.
// Lists every deep-dive (scanned server-side from deep-dives/*.json), lets the
// user read inline, delete, regenerate, and manually create a new one.
import { $, escapeHtml, fmtDate } from './util.js';
import { api, renderMermaidInside } from './api.js';
import { renderMarkdown } from './markdown.js';
import { switchView } from './nav.js';

// aid → desired action when the dives view next loads ('open' | 'generate').
let pendingAction = null;

export async function loadDives() {
  const listEl = $('#dives-list');
  listEl.innerHTML = '<div class="muted-card">加载中…</div>';
  let items = [];
  try {
    items = await api('GET', '/api/ai-news/deep-dives');
  } catch (e) {
    listEl.innerHTML = '<div class="muted-card">❌ 加载失败：' + escapeHtml(e.message) + '</div>';
    return;
  }
  $('#cnt-dives').textContent = items.length;
  if (!items.length) {
    listEl.innerHTML = '<div class="muted-card" style="padding:40px 16px;text-align:center">'
      + '🧠 还没有深度解读。<br><span class="text-faint" style="font-size:12px">'
      + '去文章流点「深度解读」，或在上方手动输入主题生成一篇。</span></div>';
  } else {
    listEl.innerHTML = items.map(diveItemHtml).join('');
    listEl.querySelectorAll('[data-dive-row]').forEach(row => {
      const aid = row.dataset.diveRow;
      row.querySelector('[data-act="read"]')?.addEventListener('click', () => toggleRead(aid, row));
      row.querySelector('[data-act="regen"]')?.addEventListener('click', (e) => { e.stopPropagation(); regenDive(aid); });
      row.querySelector('[data-act="del"]')?.addEventListener('click', (e) => { e.stopPropagation(); delDive(aid); });
    });
  }

  // Honor a pending jump from the feed (open an existing dive, or trigger one).
  if (pendingAction) {
    const { aid, mode } = pendingAction;
    pendingAction = null;
    const row = $(`[data-dive-row="${CSS.escape(aid)}"]`);
    if (mode === 'generate' && !row) {
      await generateInto(aid);
    } else if (row) {
      row.scrollIntoView({ behavior: 'smooth', block: 'center' });
      toggleRead(aid, row);
    }
  }
}

function diveItemHtml(d) {
  const title = d.title_zh || d.title || '(无标题)';
  const manualBadge = d.is_manual ? '<span class="chip chip-tag">✍️ 手动</span>' : '';
  const origin = d.has_origin_article ? '' : '<span class="chip chip-tag" title="原文章已不在文章流">📦 已归档</span>';
  return `
    <div class="dive-row" data-dive-row="${escapeHtml(d.article_id)}">
      <div class="dive-row-head">
        <div class="dive-row-main" data-act="read" style="cursor:pointer">
          <div class="dive-row-title">${escapeHtml(title)}</div>
          <div class="dive-row-meta">${escapeHtml(d.source || '')} · ${fmtDate(d.generated_at)} ${manualBadge} ${origin}</div>
        </div>
        <div class="dive-row-actions">
          <button class="btn-card ghost sm" data-act="regen" title="重新生成">↻</button>
          <button class="btn-card ghost sm" data-act="del" title="删除">🗑</button>
        </div>
      </div>
      <div class="dive-row-body reader hidden" data-dive-body></div>
    </div>`;
}

async function toggleRead(aid, row) {
  const body = row.querySelector('[data-dive-body]');
  if (!body) return;
  if (!body.classList.contains('hidden') && body.dataset.loaded === 'true') {
    body.classList.add('hidden');
    return;
  }
  body.classList.remove('hidden');
  if (body.dataset.loaded === 'true') return;
  body.innerHTML = '<div class="muted-card">⏳ 加载中…</div>';
  try {
    const r = await api('GET', `/api/ai-news/articles/${aid}/deep-dive`);
    body.innerHTML = renderMarkdown(r.body || '');
    await renderMermaidInside(body);
    body.dataset.loaded = 'true';
  } catch (e) {
    body.innerHTML = '<div class="muted-card">❌ 加载失败：' + escapeHtml(e.message) + '</div>';
  }
}

async function regenDive(aid) {
  const row = $(`[data-dive-row="${CSS.escape(aid)}"]`);
  const body = row?.querySelector('[data-dive-body]');
  if (body) {
    body.classList.remove('hidden');
    body.dataset.loaded = '';
    body.innerHTML = '<div class="muted-card">⏳ 重新生成中（约 20–30s）…</div>';
  }
  try {
    await api('POST', `/api/ai-news/articles/${aid}/deep-dive`);
    await loadDives();
    const fresh = $(`[data-dive-row="${CSS.escape(aid)}"]`);
    if (fresh) toggleRead(aid, fresh);
  } catch (e) {
    if (body) body.innerHTML = '<div class="muted-card">❌ 生成失败：' + escapeHtml(e.message) + '</div>';
  }
}

async function delDive(aid) {
  if (!confirm('删除这篇深度解读？')) return;
  try {
    await api('DELETE', `/api/ai-news/articles/${aid}/deep-dive`);
    await loadDives();
  } catch (e) { alert('删除失败：' + e.message); }
}

// Generate a dive for an article id straight into this view (used when the feed
// triggers a not-yet-generated dive).
async function generateInto(aid) {
  const listEl = $('#dives-list');
  const banner = document.createElement('div');
  banner.className = 'muted-card';
  banner.innerHTML = '⏳ 正在生成深度解读（约 20–30s）…';
  listEl.prepend(banner);
  try {
    await api('POST', `/api/ai-news/articles/${aid}/deep-dive`);
  } catch (e) {
    banner.innerHTML = '❌ 生成失败：' + escapeHtml(e.message);
    return;
  }
  await loadDives();
  const row = $(`[data-dive-row="${CSS.escape(aid)}"]`);
  if (row) { row.scrollIntoView({ behavior: 'smooth', block: 'center' }); toggleRead(aid, row); }
}

// Manual new dive from a user-supplied topic (entry now lives in this view).
export async function manualNewDive() {
  const topic = $('#dive-topic').value.trim();
  if (!topic) return alert('请输入主题');
  const s = $('#dive-status'); s.textContent = '⏳ 生成中（约 20–30s）…';
  try {
    const r = await api('POST', '/api/ai-news/manual-dive', { topic });
    $('#dive-topic').value = '';
    s.textContent = '✓ 已生成';
    await loadDives();
    const aid = r.article_id;
    const row = aid && $(`[data-dive-row="${CSS.escape(aid)}"]`);
    if (row) { row.scrollIntoView({ behavior: 'smooth', block: 'center' }); toggleRead(aid, row); }
  } catch (e) { s.textContent = '❌ ' + e.message; }
}

// Called from the feed: jump to this view and open (or generate) a dive.
export function jumpToDive(aid, { generate = false } = {}) {
  pendingAction = { aid, mode: generate ? 'generate' : 'open' };
  switchView('dives');
}
