// Auth: login state, header bar, login/register modal, and UI gating.
// Anonymous users can browse (view) everything; writes / LLM calls return 401,
// which surfaces the login modal (wired via api.setUnauthorizedHandler).
import { $ } from './util.js';
import { api, setUnauthorizedHandler } from './api.js';

let currentUser = null;
export function getUser() { return currentUser; }
export function isAuthed() { return !!currentUser; }

// ── boot ──────────────────────────────────────────────────────────────
export async function initAuth() {
  setUnauthorizedHandler(() => openAuthModal('请先登录后再操作'));
  buildModal();
  try {
    const r = await api('GET', '/api/auth/me');
    currentUser = r.user || null;
  } catch (e) { currentUser = null; }
  renderAuthBar();
  applyGating();
}

// ── header bar (top-right) ─────────────────────────────────────────────
function renderAuthBar() {
  const slot = $('#auth-slot');
  if (!slot) return;
  if (currentUser) {
    slot.innerHTML = `
      <span class="auth-user" title="${escapeAttr(currentUser.email)}">
        ${currentUser.role === 'admin' ? '👑 ' : '👤 '}${escapeAttr(currentUser.email)}
      </span>
      <button class="ghost sm" id="btn-logout">登出</button>`;
    $('#btn-logout').addEventListener('click', doLogout);
  } else {
    slot.innerHTML = `<button class="primary sm" id="btn-login">登录 / 注册</button>`;
    $('#btn-login').addEventListener('click', () => openAuthModal());
  }
}

// Toggle a body class so CSS can grey out write controls for anon users.
function applyGating() {
  document.body.classList.toggle('is-anon', !currentUser);
  document.body.classList.toggle('is-authed', !!currentUser);
}

// ── login / register modal ─────────────────────────────────────────────
let mode = 'login'; // 'login' | 'register'

function buildModal() {
  if ($('#auth-modal')) return;
  const wrap = document.createElement('div');
  wrap.id = 'auth-modal';
  wrap.className = 'auth-modal hidden';
  wrap.innerHTML = `
    <div class="auth-card">
      <button class="auth-close" data-act="close" title="关闭">✕</button>
      <h3 id="auth-title">登录</h3>
      <p class="auth-msg" id="auth-msg"></p>
      <label class="field"><span>邮箱</span>
        <input id="auth-email" type="email" autocomplete="username" placeholder="you@example.com" /></label>
      <label class="field"><span>密码</span>
        <input id="auth-pw" type="password" autocomplete="current-password" placeholder="至少 8 位" /></label>
      <button class="primary" id="auth-submit">登录</button>
      <p class="auth-switch">
        <span id="auth-switch-text">还没有账号？</span>
        <a href="#" id="auth-switch-link">去注册</a>
      </p>
    </div>`;
  document.body.appendChild(wrap);
  wrap.addEventListener('click', (e) => { if (e.target === wrap) closeAuthModal(); });
  wrap.querySelector('[data-act="close"]').addEventListener('click', closeAuthModal);
  $('#auth-switch-link').addEventListener('click', (e) => { e.preventDefault(); setMode(mode === 'login' ? 'register' : 'login'); });
  $('#auth-submit').addEventListener('click', submitAuth);
  $('#auth-pw').addEventListener('keydown', (e) => { if (e.key === 'Enter') submitAuth(); });
}

function setMode(m) {
  mode = m;
  $('#auth-title').textContent = m === 'login' ? '登录' : '注册';
  $('#auth-submit').textContent = m === 'login' ? '登录' : '注册';
  $('#auth-switch-text').textContent = m === 'login' ? '还没有账号？' : '已有账号？';
  $('#auth-switch-link').textContent = m === 'login' ? '去注册' : '去登录';
}

export function openAuthModal(msg) {
  buildModal();
  setMode('login');
  $('#auth-msg').textContent = msg || '';
  $('#auth-msg').classList.toggle('hidden', !msg);
  $('#auth-modal').classList.remove('hidden');
  setTimeout(() => $('#auth-email').focus(), 50);
}

function closeAuthModal() {
  $('#auth-modal')?.classList.add('hidden');
}

async function submitAuth() {
  const email = $('#auth-email').value.trim();
  const password = $('#auth-pw').value;
  const msg = $('#auth-msg');
  const btn = $('#auth-submit');
  if (!email || !password) { showMsg('请填写邮箱和密码'); return; }
  btn.disabled = true; const orig = btn.textContent; btn.textContent = '处理中…';
  try {
    const r = await api('POST', `/api/auth/${mode}`, { email, password });
    currentUser = r.user;
    closeAuthModal();
    renderAuthBar();
    applyGating();
    // Reload data so user-scoped views reflect the logged-in identity.
    window.dispatchEvent(new CustomEvent('aif:auth-changed'));
  } catch (e) {
    showMsg(e.message || '操作失败');
  } finally {
    btn.disabled = false; btn.textContent = orig;
  }
}

function showMsg(t) {
  const msg = $('#auth-msg');
  msg.textContent = t;
  msg.classList.remove('hidden');
}

async function doLogout() {
  try { await api('POST', '/api/auth/logout'); } catch (e) { /* ignore */ }
  currentUser = null;
  // Drop the chat conversation id so the next user doesn't resume this thread.
  try { localStorage.removeItem('aif_conv_id'); } catch (e) { /* ignore */ }
  renderAuthBar();
  applyGating();
  window.dispatchEvent(new CustomEvent('aif:auth-changed'));
}

function escapeAttr(s) {
  return String(s || '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
