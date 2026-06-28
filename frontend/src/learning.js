// Personalized learning path view: generate a staged roadmap, browse saved ones.
import { $, escapeHtml, fmtDate } from './util.js';
import { api } from './api.js';
import { jumpToDive } from './dives.js';
import { switchView } from './nav.js';

export async function loadLearning() {
  await renderSuggestions();
  await renderList();
  renderCurrent(null);
}

async function renderSuggestions() {
  const box = $('#lp-suggestions');
  if (!box) return;
  try {
    const r = await api('GET', '/api/ai-news/learning-paths/suggestions');
    if (!r.items?.length) { box.innerHTML = ''; return; }
    box.innerHTML = '<span class="text-faint text-xs">推荐方向：</span>' +
      r.items.map(d => `<button class="chip chip-suggest" data-dir="${escapeHtml(d)}">${escapeHtml(d)}</button>`).join('');
    box.querySelectorAll('[data-dir]').forEach(b =>
      b.addEventListener('click', () => { $('#lp-topic').value = b.dataset.dir; $('#lp-topic').focus(); }));
  } catch (e) { box.innerHTML = ''; }
}

async function renderList() {
  const box = $('#learning-list');
  try {
    const r = await api('GET', '/api/ai-news/learning-paths');
    $('#learning-meta').textContent = r.total ? `已有 ${r.total} 条路径` : '';
    if (!r.total) {
      box.innerHTML = '<div class="text-faint text-xs">还没有学习路径。输入一个方向，生成你的第一条。</div>';
      return;
    }
    box.innerHTML = r.items.map(p => `
      <div class="lp-list-item" data-slug="${escapeHtml(p.slug)}">
        <span class="lp-list-topic">${escapeHtml(p.topic)}</span>
        <span class="text-faint text-xs">${p.stage_count} 阶段 · ${p.generated_at ? fmtDate(p.generated_at) : ''}</span>
        <button class="btn-card ghost sm" data-del="${escapeHtml(p.slug)}">🗑</button>
      </div>`).join('');
    box.querySelectorAll('.lp-list-item').forEach(el => {
      el.addEventListener('click', (e) => {
        if (e.target.closest('[data-del]')) return;
        openPath(el.dataset.slug);
      });
    });
    box.querySelectorAll('[data-del]').forEach(b =>
      b.addEventListener('click', () => deletePath(b.dataset.del)));
  } catch (e) {
    box.innerHTML = '<div class="muted-card">❌ ' + escapeHtml(e.message) + '</div>';
  }
}

async function openPath(slug) {
  try {
    const r = await api('GET', `/api/ai-news/learning-paths/${slug}`);
    renderCurrent(r);
  } catch (e) { alert('打开失败：' + e.message); }
}

async function deletePath(slug) {
  if (!confirm('删除这条学习路径？')) return;
  try {
    await api('DELETE', `/api/ai-news/learning-paths/${slug}`);
    await renderList();
    renderCurrent(null);
  } catch (e) { alert('删除失败：' + e.message); }
}

export async function generateLearning() {
  const topic = $('#lp-topic').value.trim();
  if (!topic) { alert('请输入一个学习方向'); return; }
  const box = $('#learning-current');
  box.innerHTML = '<div class="muted-card">⏳ 生成中（约 20-30s）…</div>';
  try {
    const r = await api('POST', '/api/ai-news/learning-paths/generate', { topic });
    $('#lp-topic').value = '';
    await renderList();
    renderCurrent(r);
  } catch (e) {
    box.innerHTML = '<div class="muted-card">❌ ' + escapeHtml(e.message) + '</div>';
  }
}

function renderCurrent(path) {
  const box = $('#learning-current');
  if (!path) { box.innerHTML = ''; return; }
  const stages = (path.stages || []).map((s, i) => {
    const learn = (s.learn || []).map(x => `<li>${escapeHtml(x)}</li>`).join('');
    const reads = (s.read || []).map(r => `
      <div class="lp-read" data-type="${escapeHtml(r.type)}" data-id="${escapeHtml(r.id)}" data-url="${escapeHtml(r.url || '')}">
        ${r.type === 'deep-dive' ? '🧠' : '📰'} ${escapeHtml(r.title)}
        ${r.note ? `<span class="text-faint"> · ${escapeHtml(r.note)}</span>` : ''}
      </div>`).join('');
    const suggest = s.suggest ? `<div class="lp-suggest text-faint">💡 ${escapeHtml(s.suggest)}</div>` : '';
    const practice = s.practice ? `<div class="lp-practice">🛠 ${escapeHtml(s.practice)}</div>` : '';
    return `
      <div class="lp-stage">
        <div class="lp-stage-head"><span class="lp-stage-num">${i + 1}</span>
          <div><b>${escapeHtml(s.title)}</b><div class="text-faint text-xs">${escapeHtml(s.goal || '')}</div></div>
        </div>
        ${learn ? `<ul class="lp-learn">${learn}</ul>` : ''}
        ${reads}
        ${suggest}
        ${practice}
      </div>`;
  }).join('');
  box.innerHTML = `
    <div class="lp-path-head">
      <h4>🗺️ ${escapeHtml(path.topic)}</h4>
      ${path.based_on_profile ? '<span class="chip chip-tag">已结合你的画像</span>' : ''}
    </div>
    <div class="lp-stages">${stages}</div>`;

  box.querySelectorAll('.lp-read').forEach(el => el.addEventListener('click', () => {
    const { type, id, url } = el.dataset;
    if (type === 'deep-dive') { switchView('dives'); jumpToDive(id, { generate: false }); }
    else if (url) { window.open(url, '_blank', 'noopener'); }
  }));
}
