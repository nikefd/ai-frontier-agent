// DOM helpers and formatting utilities.

export const $ = (sel, root) => (root || document).querySelector(sel);
export const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

export function escapeHtml(s) {
  return String(s || '').replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

export function safeExternalUrl(value) {
  try {
    const url = new URL(String(value || ''));
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : '';
  } catch (e) {
    return '';
  }
}

export function fmtDate(s) {
  if (!s) return '';
  try {
    const d = new Date(s);
    if (isNaN(d)) return '';
    const diff = (new Date() - d) / 1000;
    if (diff < 3600) return Math.max(1, Math.floor(diff / 60)) + ' 分钟前';
    if (diff < 86400) return Math.floor(diff / 3600) + ' 小时前';
    if (diff < 86400 * 7) return Math.floor(diff / 86400) + ' 天前';
    return d.toISOString().slice(0, 10);
  } catch (e) { return ''; }
}

const CAT_LABELS = {
  vendor: '🏢 官方', media: '📰 媒体', blog: '📝 博客', paper: '📄 论文',
  community: '🌐 社区', expert: '✍️ 专家', 'x-ai': '𝕏 大V', trending: '🔥 风向',
};

export function catBadge(c) {
  if (!c) return '';
  const safe = escapeHtml(c);
  return `<span class="tier-badge tier-${safe}" title="${safe}">${escapeHtml(CAT_LABELS[c] || c)}</span>`;
}
