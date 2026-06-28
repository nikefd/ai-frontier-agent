// Knowledge cards + spaced-repetition review view.
// Two panes: 今日复习 (flip-and-grade flow) and 卡片管理 (list / delete / add).
import { $, escapeHtml, fmtDate } from './util.js';
import { api } from './api.js';

let dueQueue = [];   // cards due today, consumed one by one
let flipped = false;

export async function loadReview() {
  await renderDue();
  await renderManage();
}

// ── Today's review ───────────────────────────────────────────────────
async function renderDue() {
  const box = $('#review-due');
  box.innerHTML = '<div class="muted-card">加载中…</div>';
  try {
    const r = await api('GET', '/api/ai-news/review/due');
    $('#review-due-meta').textContent = `今日待复习 ${r.due_count} 张 · 卡片库共 ${r.total} 张`;
    dueQueue = r.items || [];
    flipped = false;
    showCurrentCard();
  } catch (e) {
    box.innerHTML = '<div class="muted-card">❌ ' + escapeHtml(e.message) + '</div>';
  }
}

function showCurrentCard() {
  const box = $('#review-due');
  if (!dueQueue.length) {
    box.innerHTML = '<div class="muted-card" style="padding:40px 20px;text-align:center">🎉 今天复习完啦，没有到期卡片了</div>';
    return;
  }
  const c = dueQueue[0];
  box.innerHTML = `
    <div class="srs-card">
      <div class="srs-front">${escapeHtml(c.front)}</div>
      ${flipped ? `<hr class="hr"><div class="srs-back">${escapeHtml(c.back || '（无背面内容）')}</div>
        ${c.source_url ? `<a class="srs-src" href="${escapeHtml(c.source_url)}" target="_blank" rel="noopener">看原文 ↗</a>` : ''}` : ''}
      <div class="srs-controls">
        ${flipped ? `
          <button class="btn-card" data-grade="forgot">😵 忘了</button>
          <button class="btn-card" data-grade="hard">🤔 模糊</button>
          <button class="btn-card success" data-grade="good">😎 记得</button>
        ` : `<button class="btn-card accent" id="srs-flip">翻面看答案</button>`}
      </div>
      <div class="srs-progress text-faint">剩余 ${dueQueue.length} 张</div>
    </div>`;

  $('#srs-flip')?.addEventListener('click', () => { flipped = true; showCurrentCard(); });
  box.querySelectorAll('[data-grade]').forEach(btn =>
    btn.addEventListener('click', () => gradeCurrent(btn.dataset.grade)));
}

async function gradeCurrent(grade) {
  const c = dueQueue[0];
  if (!c) return;
  try {
    await api('POST', `/api/ai-news/review/cards/${c.id}/grade`, { grade });
    dueQueue.shift();
    flipped = false;
    showCurrentCard();
    $('#review-due-meta').textContent = `本次还剩 ${dueQueue.length} 张`;
  } catch (e) {
    alert('提交失败：' + e.message);
  }
}

// ── Card management ──────────────────────────────────────────────────
async function renderManage() {
  const box = $('#review-list');
  box.innerHTML = '<div class="muted-card">加载中…</div>';
  try {
    const r = await api('GET', '/api/ai-news/review/cards');
    $('#cnt-review').textContent = r.total;
    if (!r.total) {
      box.innerHTML = '<div class="muted-card">还没有卡片。在文章流点「🗂️ 加入复习」，或下方手动新建。</div>';
      return;
    }
    box.innerHTML = r.items.map(cardRow).join('');
    box.querySelectorAll('[data-del]').forEach(btn =>
      btn.addEventListener('click', () => deleteCard(btn.dataset.del)));
  } catch (e) {
    box.innerHTML = '<div class="muted-card">❌ ' + escapeHtml(e.message) + '</div>';
  }
}

function cardRow(c) {
  const srs = c.srs || {};
  const src = { article: '📰 文章', 'deep-dive': '🧠 解读', manual: '✍️ 手动' }[c.source_type] || c.source_type;
  return `
    <div class="srs-row">
      <div class="srs-row-main">
        <div class="srs-row-front">${escapeHtml(c.front)}</div>
        <div class="srs-row-meta text-faint">${src} · 下次复习 ${srs.due || '—'} · 已复习 ${srs.reps || 0} 次</div>
      </div>
      <button class="btn-card ghost sm" data-del="${escapeHtml(c.id)}" title="删除">🗑</button>
    </div>`;
}

async function deleteCard(cid) {
  if (!confirm('删除这张卡片？')) return;
  try {
    await api('DELETE', `/api/ai-news/review/cards/${cid}`);
    await renderManage();
    await renderDue();
  } catch (e) { alert('删除失败：' + e.message); }
}

export async function addManualCard() {
  const front = $('#srs-new-front').value.trim();
  const back = $('#srs-new-back').value.trim();
  if (!front) { alert('请填写正面（问题）'); return; }
  try {
    await api('POST', '/api/ai-news/review/cards', { front, back, source_type: 'manual' });
    $('#srs-new-front').value = ''; $('#srs-new-back').value = '';
    await renderManage();
    await renderDue();
  } catch (e) { alert('新建失败：' + e.message); }
}
