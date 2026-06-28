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
  _handleVerifyResult();
  _handleResetLink();
}

// Show a small toast when arriving from an email verification link, then clean
// the query string so a refresh doesn't re-show it.
function _handleVerifyResult() {
  const params = new URLSearchParams(window.location.search);
  const v = params.get('verify');
  if (!v) return;
  const msg = v === 'ok' ? '✅ 邮箱验证成功' : '❌ 验证链接无效或已过期';
  const t = document.createElement('div');
  t.className = 'verify-toast';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 4000);
  params.delete('verify');
  const qs = params.toString();
  window.history.replaceState({}, '', window.location.pathname + (qs ? '?' + qs : ''));
}

// ── header bar (top-right) ─────────────────────────────────────────────
function renderAuthBar() {
  const slot = $('#auth-slot');
  if (!slot) return;
  if (currentUser) {
    const unverified = !currentUser.email_verified
      ? `<button class="ghost sm auth-unverified" id="btn-resend" title="邮箱未验证，点击重新发送验证邮件">📧 未验证</button>`
      : '';
    slot.innerHTML = `
      ${unverified}
      <span class="auth-user" title="${escapeAttr(currentUser.email)}">
        ${currentUser.role === 'admin' ? '👑 ' : '👤 '}${escapeAttr(currentUser.email)}
      </span>
      <button class="ghost sm" id="btn-change-pw" title="修改密码">🔑</button>
      <button class="ghost sm" id="btn-logout">登出</button>`;
    $('#btn-logout').addEventListener('click', doLogout);
    $('#btn-resend')?.addEventListener('click', resendVerification);
    $('#btn-change-pw').addEventListener('click', openChangePasswordModal);
  } else {
    slot.innerHTML = `<button class="primary sm" id="btn-login">登录 / 注册</button>`;
    $('#btn-login').addEventListener('click', () => openAuthModal());
  }
}

async function resendVerification(e) {
  const btn = e.currentTarget; btn.disabled = true; const orig = btn.textContent; btn.textContent = '发送中…';
  try {
    const r = await api('POST', '/api/auth/resend-verification');
    btn.textContent = r.already_verified ? '✓ 已验证' : '✓ 已发送，查收邮箱';
  } catch (err) {
    btn.textContent = '发送失败';
    setTimeout(() => { btn.disabled = false; btn.textContent = orig; }, 2000);
  }
}

// Toggle a body class so CSS can grey out write controls for anon users.
function applyGating() {
  document.body.classList.toggle('is-anon', !currentUser);
  document.body.classList.toggle('is-authed', !!currentUser);
  document.body.classList.toggle('is-admin', currentUser?.role === 'admin');
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
        <a href="#" id="auth-forgot-link" style="margin-left:auto">忘记密码？</a>
      </p>
    </div>`;
  document.body.appendChild(wrap);
  wrap.addEventListener('click', (e) => { if (e.target === wrap) closeAuthModal(); });
  wrap.querySelector('[data-act="close"]').addEventListener('click', closeAuthModal);
  $('#auth-switch-link').addEventListener('click', (e) => { e.preventDefault(); setMode(mode === 'login' ? 'register' : 'login'); });
  $('#auth-forgot-link').addEventListener('click', (e) => { e.preventDefault(); closeAuthModal(); openForgotModal(); });
  $('#auth-submit').addEventListener('click', submitAuth);
  $('#auth-pw').addEventListener('keydown', (e) => { if (e.key === 'Enter') submitAuth(); });
}

function setMode(m) {
  mode = m;
  $('#auth-title').textContent = m === 'login' ? '登录' : '注册';
  $('#auth-submit').textContent = m === 'login' ? '登录' : '注册';
  $('#auth-switch-text').textContent = m === 'login' ? '还没有账号？' : '已有账号？';
  $('#auth-switch-link').textContent = m === 'login' ? '去注册' : '去登录';
  $('#auth-forgot-link')?.classList.toggle('hidden', m !== 'login');
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

// ── Lightweight single-purpose modal (forgot / change / reset password) ──
// Renders into a shared #pw-modal node; `fields` is [{id,label,type,placeholder}],
// onSubmit(values) returns a message string on success or throws on error.
function openPwModal({ title, fields, submitText, onSubmit }) {
  document.getElementById('pw-modal')?.remove();
  const wrap = document.createElement('div');
  wrap.id = 'pw-modal';
  wrap.className = 'auth-modal';
  wrap.innerHTML = `
    <div class="auth-card">
      <button class="auth-close" data-act="close" title="关闭">✕</button>
      <h3>${escapeAttr(title)}</h3>
      <p class="auth-msg hidden" id="pw-msg"></p>
      ${fields.map(f => `
        <label class="field"><span>${escapeAttr(f.label)}</span>
          <input id="${f.id}" type="${f.type || 'password'}" placeholder="${escapeAttr(f.placeholder || '')}" /></label>`).join('')}
      <button class="primary" id="pw-submit">${escapeAttr(submitText)}</button>
    </div>`;
  document.body.appendChild(wrap);
  const close = () => wrap.remove();
  wrap.addEventListener('click', (e) => { if (e.target === wrap) close(); });
  wrap.querySelector('[data-act="close"]').addEventListener('click', close);
  const submit = async () => {
    const values = {};
    fields.forEach(f => { values[f.id] = document.getElementById(f.id).value; });
    const btn = $('#pw-submit'); btn.disabled = true; const orig = btn.textContent; btn.textContent = '处理中…';
    try {
      const okMsg = await onSubmit(values);
      const msg = $('#pw-msg'); msg.textContent = okMsg || '完成'; msg.classList.remove('hidden');
      setTimeout(close, 1200);
    } catch (e) {
      const msg = $('#pw-msg'); msg.textContent = e.message || '操作失败'; msg.classList.remove('hidden');
      btn.disabled = false; btn.textContent = orig;
    }
  };
  $('#pw-submit').addEventListener('click', submit);
  wrap.querySelectorAll('input').forEach(i =>
    i.addEventListener('keydown', (e) => { if (e.key === 'Enter') submit(); }));
  setTimeout(() => wrap.querySelector('input')?.focus(), 50);
}

export function openChangePasswordModal() {
  openPwModal({
    title: '修改密码',
    submitText: '保存',
    fields: [
      { id: 'cp-old', label: '当前密码', placeholder: '当前密码' },
      { id: 'cp-new', label: '新密码', placeholder: '至少 8 位' },
    ],
    onSubmit: async (v) => {
      await api('POST', '/api/auth/change-password', { old_password: v['cp-old'], new_password: v['cp-new'] });
      return '✅ 密码已修改';
    },
  });
}

function openForgotModal() {
  openPwModal({
    title: '找回密码',
    submitText: '发送重置链接',
    fields: [{ id: 'fp-email', label: '邮箱', type: 'email', placeholder: 'you@example.com' }],
    onSubmit: async (v) => {
      await api('POST', '/api/auth/forgot-password', { email: (v['fp-email'] || '').trim() });
      return '📧 若邮箱已注册，重置链接已发出，请查收';
    },
  });
}

function openResetModal(token) {
  openPwModal({
    title: '设置新密码',
    submitText: '重置并登录',
    fields: [{ id: 'rp-new', label: '新密码', placeholder: '至少 8 位' }],
    onSubmit: async (v) => {
      const r = await api('POST', '/api/auth/reset-password', { token, new_password: v['rp-new'] });
      currentUser = r.user;
      renderAuthBar(); applyGating();
      window.dispatchEvent(new CustomEvent('aif:auth-changed'));
      return '✅ 密码已重置，已为你登录';
    },
  });
}

// Detect a reset link (?reset=<token>), open the reset form, and clean the URL.
function _handleResetLink() {
  const params = new URLSearchParams(window.location.search);
  const token = params.get('reset');
  if (!token) return;
  params.delete('reset');
  const qs = params.toString();
  window.history.replaceState({}, '', window.location.pathname + (qs ? '?' + qs : ''));
  openResetModal(token);
}
