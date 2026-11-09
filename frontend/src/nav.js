import { uiText, uiTemplate } from './i18n.js';
// View switching + URL routing (History API). Extracted so feed.js / dives.js
// can trigger navigation without importing main.js (avoids an import cycle).
import { $, $$ } from './util.js';
import { state } from './state.js';
import { refreshList } from './feed.js';
import { loadSummary, loadSources, loadProfile, loadForYou } from './views.js';
import { loadDives } from './dives.js';
import { loadReview } from './review.js';
import { loadReflection } from './reflection.js';
import { loadLearning } from './learning.js';
import { loadAdminUsers } from './admin.js';
import { loadSuggestions } from './suggestions.js';
import { loadExperiments } from './experiments.js';
import { readFeedRoute, syncFeedControls } from './feed-route.js';

// All routable views. The landing/home page is the root path "/".
const VIEWS = ['feed', 'foryou', 'summary', 'dives', 'review', 'reflection',
               'profile', 'sources', 'admin', 'learning', 'experiments'];

const VIEW_META = {
  summary: [uiText('今日速报'), uiText('先用几分钟掌握今天最值得关注的 AI 动态')],
  feed: [uiText('最新文章'), uiText('来自精选信源的最新 AI 动态')],
  foryou: [uiText('为你推荐'), uiText('根据你的收藏、追踪和阅读偏好排序')],
  dives: [uiText('深度解读'), uiText('把值得关注的主题读深、读懂')],
  review: [uiText('知识卡'), uiText('复习并沉淀读过的内容')],
  reflection: [uiText('复盘'), uiText('回顾最近的关注方向和行动')],
  learning: [uiText('学习路径'), uiText('围绕一个主题建立阶段化学习路线')],
  experiments: [uiText('实验室'), uiText('把前沿资讯变成短小、可验证的实践')],
  profile: [uiText('我的画像'), uiText('查看 AI 对你关注方向的理解')],
  sources: [uiText('数据源'), uiText('查看信源覆盖与抓取状态')],
  admin: [uiText('用户管理'), uiText('管理站点用户与权限')],
};

function _runLoader(v) {
  if (v === 'feed') { refreshList(); loadSuggestions(); }
  if (v === 'foryou') loadForYou();
  if (v === 'summary') loadSummary();
  if (v === 'dives') loadDives();
  if (v === 'review') loadReview();
  if (v === 'reflection') loadReflection();
  if (v === 'learning') loadLearning();
  if (v === 'experiments') loadExperiments();
  if (v === 'profile') loadProfile();
  if (v === 'sources') loadSources();
  if (v === 'admin') loadAdminUsers();
}

// Switch view + update the URL. `push` is false when driven by popstate / boot
// (the URL is already correct, so we must not push a duplicate history entry).
export function switchView(v, push = true) {
  state.view = v;
  document.body.classList.remove('landing-active');
  document.body.dataset.view = v;
  const [title, desc] = VIEW_META[v] || [uiText('AI 前沿'), ''];
  $('#current-view-title').textContent = title;
  $('#current-view-desc').textContent = desc;
  $$('.side-nav button[data-view]').forEach(b => b.classList.toggle('on', b.dataset.view === v));
  const activeSideButton = document.querySelector(`.side-more button[data-view="${v}"]`);
  if (activeSideButton) activeSideButton.closest('.side-more').open = true;
  // Keep the mobile bottom tab highlight in sync (views not in the tab bar
  // simply leave all tabs unhighlighted).
  $$('.bottom-tabs button[data-view]').forEach(b => b.classList.toggle('on', b.dataset.view === v));
  $$('.view-pane').forEach(p => p.classList.toggle('hidden', p.id !== 'view-' + v));
  if (push && location.pathname !== '/' + v) history.pushState({ v }, '', '/' + v + location.search);
  _runLoader(v);
}

// Show the landing/home page (root path).
export function showLanding(push = true) {
  state.view = 'home';
  document.body.classList.add('landing-active');
  delete document.body.dataset.view;
  if (push && location.pathname !== '/') history.pushState({ v: 'home' }, '', '/' + location.search);
}

// Resolve the current URL path to a view on boot / back-forward navigation.
export function applyRoute() {
  const seg = location.pathname.replace(/^\/+/, '').split('/')[0];
  if (seg === 'feed') {
    Object.assign(state, readFeedRoute(location.search));
    syncFeedControls(state);
  }
  if (VIEWS.includes(seg)) switchView(seg, false);
  else showLanding(false);
}

// Browser back/forward.
window.addEventListener('popstate', applyRoute);

