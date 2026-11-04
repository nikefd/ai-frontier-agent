import { uiText, uiTemplate, isEnglish } from './i18n.js';
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
    if (isEnglish()) {
      const relative = new Intl.RelativeTimeFormat('en', {numeric:'always'});
      if (diff < 3600) return relative.format(-Math.max(1, Math.floor(diff / 60)), 'minute');
      if (diff < 86400) return relative.format(-Math.floor(diff / 3600), 'hour');
      if (diff < 86400 * 7) return relative.format(-Math.floor(diff / 86400), 'day');
    }
    if (diff < 3600) return Math.max(1, Math.floor(diff / 60)) + uiText(' 分钟前');
    if (diff < 86400) return Math.floor(diff / 3600) + uiText(' 小时前');
    if (diff < 86400 * 7) return Math.floor(diff / 86400) + uiText(' 天前');
    return d.toISOString().slice(0, 10);
  } catch (e) { return ''; }
}

const CAT_LABELS = {
  vendor: uiText('🏢 官方'), media: uiText('📰 媒体'), blog: uiText('📝 博客'), paper: uiText('📄 论文'),
  community: uiText('🌐 社区'), expert: uiText('✍️ 专家'), 'x-ai': uiText('𝕏 大V'), trending: uiText('🔥 风向'),
};

export function catBadge(c) {
  if (!c) return '';
  const safe = escapeHtml(c);
  return `<span class="tier-badge tier-${safe}" title="${safe}">${escapeHtml(CAT_LABELS[c] || c)}</span>`;
}
