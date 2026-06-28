// Admin user management view (admin-only; nav entry hidden via body.is-admin).
import { $, escapeHtml, fmtDate } from './util.js';
import { api } from './api.js';

export async function loadAdminUsers() {
  const box = $('#admin-users');
  box.innerHTML = '<div class="muted-card">加载中…</div>';
  try {
    const r = await api('GET', '/api/admin/users');
    $('#admin-meta').textContent = `共 ${r.total} 个用户`;
    box.innerHTML = `
      <table class="admin-table">
        <thead><tr>
          <th>邮箱</th><th>角色</th><th>注册</th><th>最后登录</th><th>产物</th><th>操作</th>
        </tr></thead>
        <tbody>${r.items.map(u => userRow(u, r.me)).join('')}</tbody>
      </table>`;
    bindRows(r.me);
  } catch (e) {
    box.innerHTML = '<div class="muted-card">❌ ' + escapeHtml(e.message) + '</div>';
  }
}

function userRow(u, meId) {
  const self = u.id === meId;
  const a = u.artifacts || {};
  const roleCell = self
    ? `<span class="chip">${u.role === 'admin' ? '👑 admin' : 'user'}（你）</span>`
    : `<select data-role="${escapeHtml(u.id)}">
         <option value="user" ${u.role === 'user' ? 'selected' : ''}>user</option>
         <option value="admin" ${u.role === 'admin' ? 'selected' : ''}>admin</option>
       </select>`;
  const delCell = self
    ? '<span class="text-faint">—</span>'
    : `<button class="btn-card ghost sm" data-del="${escapeHtml(u.id)}" data-email="${escapeHtml(u.email)}">🗑 删除</button>`;
  return `
    <tr>
      <td>${escapeHtml(u.email)}</td>
      <td>${roleCell}</td>
      <td class="text-faint">${u.created_at ? fmtDate(u.created_at) : '—'}</td>
      <td class="text-faint">${u.last_login_at ? fmtDate(u.last_login_at) : '—'}</td>
      <td class="text-faint">📌${a.pins || 0} 🧠${a.deep_dives || 0} 🗂️${a.cards || 0}</td>
      <td>${delCell}</td>
    </tr>`;
}

function bindRows() {
  $('#admin-users').querySelectorAll('[data-role]').forEach(sel =>
    sel.addEventListener('change', async () => {
      const uid = sel.dataset.role, role = sel.value;
      try {
        await api('PATCH', `/api/admin/users/${uid}/role`, { role });
        await loadAdminUsers();
      } catch (e) { alert('改角色失败：' + e.message); await loadAdminUsers(); }
    }));
  $('#admin-users').querySelectorAll('[data-del]').forEach(btn =>
    btn.addEventListener('click', async () => {
      const uid = btn.dataset.del, email = btn.dataset.email;
      if (!confirm(`删除用户「${email}」？\n\n这会一并删除该用户的全部收藏、深度解读、知识卡和对话历史，且不可恢复。`)) return;
      try {
        await api('DELETE', `/api/admin/users/${uid}`);
        await loadAdminUsers();
      } catch (e) { alert('删除失败：' + e.message); }
    }));
}
