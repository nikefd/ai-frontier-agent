// AI reflection coach view: weekly Socratic review.
// Generate a recap + questions; each question can be taken into the chat agent
// or saved as a knowledge card.
import { $, escapeHtml, fmtDate } from './util.js';
import { api } from './api.js';
import { renderMarkdownInline } from './markdown.js';

export async function loadReflection() {
  const body = $('#reflection-body'), meta = $('#reflection-meta');
  body.innerHTML = '<div class="muted-card">加载中…</div>';
  try {
    const r = await api('GET', '/api/ai-news/reflection');
    if (r.status === 'ok' && r.questions?.length) {
      meta.textContent = r.generated_at ? '生成于 ' + fmtDate(r.generated_at) : '';
      render(r);
    } else {
      meta.textContent = '';
      body.innerHTML = `<div class="muted-card" style="padding:32px 20px">
        🪞 还没有本周复盘<br>
        <span class="text-faint" style="font-size:12px">点右上「开始本周复盘」，会基于你最近 7 天的收藏 / 解读 / 知识卡 / 对话，生成回顾和几个引导你思考的问题。</span>
      </div>`;
    }
  } catch (e) {
    body.innerHTML = '<div class="muted-card">❌ ' + escapeHtml(e.message) + '</div>';
  }
}

export async function regenReflection() {
  const body = $('#reflection-body');
  body.innerHTML = '<div class="muted-card">⏳ 生成中（约 15-25s）…</div>';
  try {
    const r = await api('POST', '/api/ai-news/reflection/generate');
    $('#reflection-meta').textContent = '生成于刚才';
    render(r);
  } catch (e) {
    body.innerHTML = '<div class="muted-card">❌ ' + escapeHtml(e.message) + '</div>';
  }
}

function render(r) {
  const body = $('#reflection-body');
  const recap = r.recap ? `<div class="reflection-recap">${renderMarkdownInline(r.recap)}</div>` : '';
  const questions = (r.questions || []).map((q, i) => `
    <div class="reflection-q">
      <div class="reflection-q-text">${escapeHtml(q)}</div>
      <div class="reflection-q-actions">
        <button class="btn-card accent sm" data-ask="${i}">💬 展开聊</button>
        <button class="btn-card ghost sm" data-card="${i}">🗂️ 存为卡片</button>
      </div>
    </div>`).join('');
  body.innerHTML = recap + questions;

  r.questions.forEach((q, i) => {
    body.querySelector(`[data-ask="${i}"]`)?.addEventListener('click', () => askInChat(q));
    body.querySelector(`[data-card="${i}"]`)?.addEventListener('click', (e) => saveAsCard(q, e.currentTarget));
  });
}

// Open the chat widget, prefill the question and send it.
function askInChat(question) {
  const chat = window.__sparrowChat;
  if (!chat) { alert('对话助手未就绪'); return; }
  chat.toggle(true);
  chat.input.value = question;
  chat.send();
}

async function saveAsCard(question, btn) {
  const orig = btn.textContent; btn.disabled = true; btn.textContent = '⏳';
  try {
    await api('POST', '/api/ai-news/review/cards', {
      front: question, source_type: 'manual',
    });
    btn.textContent = '✓ 已存';
  } catch (e) {
    btn.textContent = '❌ 失败';
    setTimeout(() => { btn.disabled = false; btn.textContent = orig; }, 1600);
  }
}
