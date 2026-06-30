// Proactive nudges bar (B2): the agent suggesting the next step.
// Renders dismissible suggestion bars above the feed; action → jump to a view.
// Dismissed ids are remembered in localStorage so we don't nag.
import { $, escapeHtml } from './util.js';
import { api } from './api.js';
import { switchView } from './nav.js';

const DISMISS_KEY = 'aif_dismissed_suggestions';

function dismissed() {
  try { return JSON.parse(localStorage.getItem(DISMISS_KEY) || '[]'); } catch (e) { return []; }
}
function dismiss(id) {
  const d = dismissed(); if (!d.includes(id)) d.push(id);
  try { localStorage.setItem(DISMISS_KEY, JSON.stringify(d)); } catch (e) { /* ignore */ }
}

export async function loadSuggestions() {
  const bar = $('#suggestions-bar');
  if (!bar) return;
  try {
    const r = await api('GET', '/api/ai-news/suggestions');
    const seen = dismissed();
    const items = (r.items || []).filter(s => !seen.includes(s.id));
    if (!items.length) { bar.innerHTML = ''; return; }
    bar.innerHTML = items.map(s => `
      <div class="suggest-bar" data-id="${escapeHtml(s.id)}">
        <span class="suggest-ico">🤖</span>
        <span class="suggest-text">${renderText(s.text)}</span>
        <button class="btn-card accent sm" data-go="${escapeHtml(s.view)}">${escapeHtml(s.action)}</button>
        <button class="suggest-x" title="不再提示">✕</button>
      </div>`).join('');
    bar.querySelectorAll('.suggest-bar').forEach(el => {
      const id = el.dataset.id;
      el.querySelector('[data-go]').addEventListener('click', () => {
        dismiss(id);                       // acting on it also clears it
        switchView(el.querySelector('[data-go]').dataset.go);
      });
      el.querySelector('.suggest-x').addEventListener('click', () => {
        dismiss(id);
        el.remove();
      });
    });
  } catch (e) { bar.innerHTML = ''; }
}

// Minimal **bold** rendering (suggestions use it for emphasis), escaped first.
function renderText(t) {
  return escapeHtml(t).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
}
