// View switching + URL routing (History API). Extracted so feed.js / dives.js
// can trigger navigation without importing main.js (avoids an import cycle).
import { $$ } from './util.js';
import { state } from './state.js';
import { refreshList } from './feed.js';
import { loadSummary, loadSources, loadProfile, loadForYou } from './views.js';
import { loadDives } from './dives.js';
import { loadReview } from './review.js';
import { loadReflection } from './reflection.js';
import { loadLearning } from './learning.js';
import { loadAdminUsers } from './admin.js';

// All routable views. The landing/home page is the root path "/".
const VIEWS = ['feed', 'foryou', 'summary', 'dives', 'review', 'reflection',
               'profile', 'sources', 'admin', 'learning'];

function _runLoader(v) {
  if (v === 'feed') refreshList();
  if (v === 'foryou') loadForYou();
  if (v === 'summary') loadSummary();
  if (v === 'dives') loadDives();
  if (v === 'review') loadReview();
  if (v === 'reflection') loadReflection();
  if (v === 'learning') loadLearning();
  if (v === 'profile') loadProfile();
  if (v === 'sources') loadSources();
  if (v === 'admin') loadAdminUsers();
}

// Switch view + update the URL. `push` is false when driven by popstate / boot
// (the URL is already correct, so we must not push a duplicate history entry).
export function switchView(v, push = true) {
  state.view = v;
  document.body.classList.remove('landing-active');
  $$('.side-nav button[data-view]').forEach(b => b.classList.toggle('on', b.dataset.view === v));
  $$('.view-pane').forEach(p => p.classList.toggle('hidden', p.id !== 'view-' + v));
  if (push && location.pathname !== '/' + v) history.pushState({ v }, '', '/' + v);
  _runLoader(v);
}

// Show the landing/home page (root path).
export function showLanding(push = true) {
  state.view = 'home';
  document.body.classList.add('landing-active');
  if (push && location.pathname !== '/') history.pushState({ v: 'home' }, '', '/');
}

// Resolve the current URL path to a view on boot / back-forward navigation.
export function applyRoute() {
  const seg = location.pathname.replace(/^\/+/, '').split('/')[0];
  if (VIEWS.includes(seg)) switchView(seg, false);
  else showLanding(false);
}

// Browser back/forward.
window.addEventListener('popstate', applyRoute);

