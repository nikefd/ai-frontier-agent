// Conversational agent: SSE streaming, tool-step chips, citations, sessions.
import { $, escapeHtml } from './util.js';
import { api } from './api.js';
import { chat } from './state.js';

function newConvId() {
  return 'c_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
}

export async function initChat() {
  await loadConversations();
  if (chat.convId) {
    await loadConversationMessages(chat.convId);
  } else if (!chat.inited) {
    $('#chat-msgs').innerHTML = '<div class="muted-card">开始一段新对话，或从右上选择历史会话。</div>';
  }
  chat.inited = true;
}

export async function loadConversations() {
  try {
    const convs = await api('GET', '/api/agent/conversations');
    const sel = $('#conv-select');
    if (!sel) return;
    sel.innerHTML = '<option value="">— 历史会话 —</option>' +
      convs.map(c => `<option value="${c.id}" ${c.id === chat.convId ? 'selected' : ''}>${escapeHtml(c.title || '新对话')} (${c.msg_count})</option>`).join('');
  } catch (e) { /* conversations endpoint optional */ }
}

export async function loadConversationMessages(convId) {
  try {
    const r = await api('GET', `/api/agent/conversations/${convId}`);
    const msgs = $('#chat-msgs');
    msgs.innerHTML = '';
    for (const m of (r.messages || [])) {
      if (m.role === 'user') {
        msgs.insertAdjacentHTML('beforeend', `<div class="msg user">${escapeHtml(m.content)}</div>`);
      } else {
        const steps = (m.tool_steps || []).map(s => `<span class="tool-chip">${escapeHtml(s.label)}: ${escapeHtml(s.summary)}</span>`).join('');
        const cites = (m.citations || []).length ? `<div class="cites">来源: ${m.citations.map(escapeHtml).join(' · ')}</div>` : '';
        msgs.insertAdjacentHTML('beforeend',
          `<div class="msg bot">${steps ? `<div class="tool-steps">${steps}</div>` : ''}${marked.parse(m.content || '')}${cites}</div>`);
      }
    }
    msgs.scrollTop = msgs.scrollHeight;
  } catch (e) { /* ignore */ }
}

export function startNewConversation() {
  chat.convId = newConvId();
  localStorage.setItem('aif_conv_id', chat.convId);
  $('#chat-msgs').innerHTML = '<div class="muted-card">新对话已开始 ✨</div>';
  const sel = $('#conv-select');
  if (sel) sel.value = '';
}

export async function chatSend() {
  if (chat.busy) return;
  const input = $('#chat-input');
  const msg = input.value.trim();
  if (!msg) return;
  input.value = '';
  if (!chat.convId) startNewConversation();

  const msgs = $('#chat-msgs');
  if (msgs.querySelector('.muted-card')) msgs.innerHTML = '';
  msgs.insertAdjacentHTML('beforeend', `<div class="msg user">${escapeHtml(msg)}</div>`);
  const botId = 'bot_' + Date.now();
  msgs.insertAdjacentHTML('beforeend',
    `<div class="msg bot" id="${botId}"><div class="tool-steps"></div><div class="bot-body"><span class="thinking">思考中…</span></div></div>`);
  const bot = document.getElementById(botId);
  const ui = { bot, stepsEl: bot.querySelector('.tool-steps'), bodyEl: bot.querySelector('.bot-body') };
  msgs.scrollTop = msgs.scrollHeight;

  chat.busy = true;
  $('#btn-chat-send').disabled = true;
  try {
    const resp = await fetch('/api/agent/chat', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ message: msg, conversation_id: chat.convId }),
    });
    if (!resp.ok || !resp.body) throw new Error('HTTP ' + resp.status);
    await consumeSse(resp.body, ui, msgs);
    loadConversations();
  } catch (e) {
    ui.bodyEl.innerHTML = `❌ ${escapeHtml(e.message)}`;
  } finally {
    chat.busy = false;
    $('#btn-chat-send').disabled = false;
  }
}

async function consumeSse(body, ui, msgs) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buf = '', finalContent = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const parts = buf.split('\n\n');
    buf = parts.pop();   // keep incomplete tail
    for (const part of parts) {
      const line = part.split('\n').find(l => l.startsWith('data:'));
      if (!line) continue;
      let ev;
      try { ev = JSON.parse(line.slice(5).trim()); } catch { continue; }
      handleChatEvent(ev, ui);
      if (ev.type === 'final') finalContent = ev.content || '';
    }
    msgs.scrollTop = msgs.scrollHeight;
  }
  if (!finalContent && !ui.bodyEl.textContent.trim()) {
    ui.bodyEl.innerHTML = '<span class="text-faint">（无回复）</span>';
  }
}

function handleChatEvent(ev, ui) {
  if (ev.type === 'title') {
    loadConversations();
  } else if (ev.type === 'tool_call') {
    const argStr = Object.entries(ev.arguments || {}).map(([k, v]) => `${k}=${v}`).join(' ');
    ui.stepsEl.insertAdjacentHTML('beforeend',
      `<span class="tool-chip running" data-tool="${escapeHtml(ev.name)}">⚙️ ${escapeHtml(ev.label || ev.name)} ${argStr ? `<em>${escapeHtml(argStr)}</em>` : ''}</span>`);
  } else if (ev.type === 'tool_result') {
    const chips = ui.stepsEl.querySelectorAll(`.tool-chip.running[data-tool="${ev.name}"]`);
    const chip = chips[chips.length - 1];
    if (chip) {
      chip.classList.remove('running');
      chip.innerHTML = `✅ ${escapeHtml(ev.label || ev.name)}: ${escapeHtml(ev.summary || '')}`;
    }
  } else if (ev.type === 'final') {
    const cites = (ev.citations || []).length
      ? `<div class="cites">来源: ${ev.citations.map(escapeHtml).join(' · ')}</div>` : '';
    ui.bodyEl.innerHTML = marked.parse(ev.content || '') + cites;
  } else if (ev.type === 'error') {
    ui.bodyEl.innerHTML = `❌ ${escapeHtml(ev.message || '出错了')}`;
  }
}
