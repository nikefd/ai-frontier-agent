// View switching — extracted so feed.js / dives.js can trigger navigation
// without importing main.js (which would create an import cycle).
import { $$ } from './util.js';
import { state } from './state.js';
import { refreshList } from './feed.js';
import { loadSummary, loadSources, loadProfile, loadForYou } from './views.js';
import { loadDives } from './dives.js';
import { loadReview } from './review.js';
import { loadReflection } from './reflection.js';
import { loadAdminUsers } from './admin.js';

export function switchView(v) {
  state.view = v;
  $$('.side-nav button[data-view]').forEach(b => b.classList.toggle('on', b.dataset.view === v));
  $$('.view-pane').forEach(p => p.classList.toggle('hidden', p.id !== 'view-' + v));
  if (v === 'feed') refreshList();
  if (v === 'foryou') loadForYou();
  if (v === 'summary') loadSummary();
  if (v === 'dives') loadDives();
  if (v === 'review') loadReview();
  if (v === 'reflection') loadReflection();
  if (v === 'profile') loadProfile();
  if (v === 'sources') loadSources();
  if (v === 'admin') loadAdminUsers();
}
