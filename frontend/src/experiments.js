// Structured experiment cards: inline article actions + persistent practice library.
import { $, escapeHtml, fmtDate, safeExternalUrl } from './util.js';
import { api } from './api.js';
import { isAuthed, openAuthModal } from './auth.js';

const STATUS_LABELS = {
  planned: '稍后实践', in_progress: '进行中', completed: '已完成',
};

function listHtml(items, empty = '暂无') {
  return items?.length
    ? `<ul>${items.map(x => `<li>${escapeHtml(x)}</li>`).join('')}</ul>`
    : `<span class="text-faint">${empty}</span>`;
}

function experimentHtml(card, { compact = false } = {}) {
  const links = (card.official_links || []).map(link => {
    const url = safeExternalUrl(link.url);
    return url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(link.label || '资料')} ↗</a>` : '';
  }).filter(Boolean).join('');
  const steps = (card.steps || []).map((step, index) => `
    <li>
      <div class="experiment-step-title"><span>${index + 1}</span>${escapeHtml(step.title)}</div>
      <div>${escapeHtml(step.action)}</div>
      ${step.expected ? `<small>预期：${escapeHtml(step.expected)}</small>` : ''}
    </li>`).join('');
  const status = card.status || 'planned';
  return `<section class="experiment-card ${compact ? 'compact' : ''}" data-experiment-id="${escapeHtml(card.article_id)}">
    <div class="experiment-head">
      <div>
        <div class="experiment-kicker">🧪 结构化实验卡</div>
        <h4>${escapeHtml(card.title || card.article_title || '未命名实验')}</h4>
      </div>
      <div class="experiment-chips"><span>${Number(card.duration_minutes) || 15} 分钟</span><span>${escapeHtml(card.difficulty || '入门')}</span></div>
    </div>
    <p class="experiment-goal">${escapeHtml(card.goal || '')}</p>
    <details ${compact ? '' : 'open'}>
      <summary>实验步骤与验收</summary>
      <div class="experiment-grid">
        <div><b>准备</b>${listHtml(card.prerequisites, '无需额外准备')}</div>
        <div><b>成功标准</b>${listHtml(card.success_criteria)}</div>
      </div>
      <ol class="experiment-steps">${steps}</ol>
      <div class="experiment-grid">
        <div><b>成本</b><p>${escapeHtml(card.cost || '未知')}</p></div>
        <div><b>风险</b>${listHtml(card.risks, '未发现额外风险')}</div>
      </div>
      ${links ? `<div class="experiment-links"><b>核验入口</b>${links}</div>` : ''}
    </details>
    <div class="experiment-record">
      <label>进度
        <select data-exp-status>
          ${Object.entries(STATUS_LABELS).map(([value, label]) => `<option value="${value}" ${value === status ? 'selected' : ''}>${label}</option>`).join('')}
        </select>
      </label>
      <label class="experiment-note">结果笔记
        <textarea data-exp-note maxlength="4000" rows="2" placeholder="记录跑通结果、失败原因或下一步…">${escapeHtml(card.note || '')}</textarea>
      </label>
      <div class="experiment-record-actions">
        <button class="ghost sm" data-exp-save>保存记录</button>
        <button class="primary sm" data-exp-coach>让 AI 带我做</button>
      </div>
    </div>
  </section>`;
}

function coach(card) {
  if (!isAuthed()) { openAuthModal('登录后即可让 AI 按实验卡带练'); return; }
  const chat = window.__sparrowChat;
  if (!chat) { alert('AI 助手未就绪'); return; }
  const steps = (card.steps || []).map((x, i) => `${i + 1}. ${x.title}：${x.action}（预期：${x.expected || '按原文核验'}）`).join('\n');
  const criteria = (card.success_criteria || []).map(x => `- ${x}`).join('\n');
  chat.toggle(true);
  chat.input.value = `请按下面这张已核验来源的实验卡，一步一步带我做。每次只给一个步骤，先确认我的环境和结果再继续；不要编造命令或 API，不确定时让我查看原文。\n\n实验：${card.title}\n目标：${card.goal}\n原文：${card.article_url || ''}\n步骤：\n${steps}\n成功标准：\n${criteria}\n\n请先检查前置条件。`;
  chat.input.focus();
  try { chat.input.setSelectionRange(chat.input.value.length, chat.input.value.length); } catch (e) { /* ignore */ }
}

function bindCard(root, card, onSaved) {
  const host = root.matches?.('[data-experiment-id]') ? root : root.querySelector('[data-experiment-id]');
  if (!host) return;
  host.querySelector('[data-exp-save]')?.addEventListener('click', async (event) => {
    const button = event.currentTarget;
    button.disabled = true; button.textContent = '保存中…';
    try {
      const updated = await api('PATCH', `/api/ai-news/articles/${card.article_id}/experiment`, {
        status: host.querySelector('[data-exp-status]').value,
        note: host.querySelector('[data-exp-note]').value,
      });
      Object.assign(card, updated);
      button.textContent = '✓ 已保存';
      onSaved?.(card);
    } catch (error) {
      button.textContent = '保存失败'; alert('保存实验记录失败：' + error.message);
    } finally {
      setTimeout(() => { button.disabled = false; button.textContent = '保存记录'; }, 1200);
    }
  });
  host.querySelector('[data-exp-coach]')?.addEventListener('click', () => coach(card));
}

export async function toggleExperiment(article, container, button) {
  if (!article || !container) return;
  if (!isAuthed()) { openAuthModal('登录后即可生成并保存实验卡'); return; }
  if (!container.classList.contains('hidden')) {
    container.classList.add('hidden');
    button.textContent = article.experiment_status ? '查看实验卡' : '生成实验卡';
    return;
  }
  button.disabled = true; button.textContent = article.experiment_status ? '加载中…' : '生成中…';
  try {
    const card = article.experiment_status
      ? await api('GET', `/api/ai-news/articles/${article.id}/experiment`)
      : await api('POST', `/api/ai-news/articles/${article.id}/experiment`, { force: false });
    article.experiment_status = card.status || 'planned';
    container.innerHTML = experimentHtml(card);
    container.classList.remove('hidden');
    bindCard(container, card, updated => {
      article.experiment_status = updated.status;
      button.textContent = updated.status === 'completed' ? '✓ 已完成' : '收起实验卡';
    });
    button.textContent = card.status === 'completed' ? '✓ 已完成' : '收起实验卡';
  } catch (error) {
    alert('实验卡操作失败：' + error.message);
    button.textContent = article.experiment_status ? '查看实验卡' : '生成实验卡';
  } finally {
    button.disabled = false;
  }
}

export async function loadExperiments() {
  const root = $('#experiments-list');
  if (!root) return;
  if (!isAuthed()) {
    root.innerHTML = '<div class="muted-card">登录后可查看你保存的实验卡与实践记录。</div>';
    $('#cnt-experiments').textContent = '·';
    return;
  }
  root.innerHTML = '<div class="muted-card">加载中…</div>';
  try {
    const result = await api('GET', '/api/ai-news/experiments');
    const items = result.items || [];
    $('#cnt-experiments').textContent = items.length;
    if (!items.length) {
      root.innerHTML = '<div class="muted-card">还没有实验卡。去“最新文章”筛选「可实践」，选一篇生成吧。</div>';
      return;
    }
    root.innerHTML = items.map(card => `<div class="experiment-library-item">
      <div class="experiment-source"><span>${escapeHtml(card.source || '')} · ${fmtDate(card.generated_at)}</span><a href="/feed">回到文章流</a></div>
      ${experimentHtml(card, { compact: true })}
    </div>`).join('');
    root.querySelectorAll('[data-experiment-id]').forEach((node, index) => bindCard(node, items[index]));
  } catch (error) {
    root.innerHTML = `<div class="muted-card">❌ 加载失败：${escapeHtml(error.message)}</div>`;
  }
}
