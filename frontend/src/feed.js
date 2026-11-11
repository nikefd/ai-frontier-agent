import { uiText, uiTemplate, isEnglish, formatCount } from './i18n.js';
// Article feed: list, render, pin, pagination. Deep-dives are read/managed in
// the separate "深度解读" view (dives.js); the feed only triggers / links to them.
import { $, escapeHtml, fmtDate, catBadge, safeExternalUrl } from './util.js';
import { api } from './api.js';
import { state } from './state.js';
import { jumpToDive } from './dives.js';
import { isAuthed, openAuthModal } from './auth.js';
import { toggleExperiment } from './experiments.js';
import { learningLinks } from './academy/learning-links.js';
import { writeFeedRoute } from './feed-route.js';

export async function refreshList() {
  if (location.pathname === '/feed') {
    history.replaceState(history.state, '', '/feed' + writeFeedRoute(location.search, state));
  }
  renderActiveFilters();
  const params = new URLSearchParams();
  params.set('offset', String(state.offset));
  params.set('limit', String(state.limit));
  if (state.cat) params.set('category', state.cat);
  if (state.q) params.set('q', state.q);
  if (state.filter === 'pinned') params.set('pinned_only', 'true');
  if (state.filter === 'translated') params.set('translated_only', 'true');
  if (state.filter === 'hands-on') params.set('hands_on_only', 'true');
  if (state.sort) params.set('sort', state.sort);
  if (state.tag) params.set('tag', state.tag);

  const listEl = $('#article-list');
  listEl.innerHTML = uiText('<div class="muted-card">加载中…</div>');
  try {
    const r = await api('GET', '/api/ai-news/articles?' + params.toString());
    const items = r.items || [];
    state.items = items;
    state.total = r.total || 0;
    $('#article-count').textContent = isEnglish() ? formatCount(state.total, 'article') : state.total + ' 篇';
    $('#cnt-feed').textContent = state.total;
    renderList();
    renderPageNav();
  } catch (e) {
    listEl.innerHTML = uiText('<div class="muted-card">❌ 加载失败：') + escapeHtml(e.message) + '</div>';
  }
}

const CAT_LABELS = {
  vendor: uiText('官方'), blog: uiText('博客'), expert: uiText('专家'), 'x-ai': uiText('大V'), community: uiText('社区'),
  media: uiText('媒体'), paper: uiText('论文'), trending: uiText('风向'),
};

function renderActiveFilters() {
  const el = $('#active-filters');
  if (!el) return;
  const filters = [];
  if (state.cat) filters.push(['cat', uiTemplate`来源：${CAT_LABELS[state.cat] || state.cat}`]);
  if (state.filter === 'pinned') filters.push(['filter', uiText('只看收藏')]);
  if (state.filter === 'translated') filters.push(['filter', uiText('只看已翻译')]);
  if (state.filter === 'hands-on') filters.push(['filter', uiText('只看可实践')]);
  if (state.tag) filters.push(['tag', uiTemplate`标签：${state.tag}`]);

  el.classList.toggle('hidden', filters.length === 0);
  el.innerHTML = filters.map(([kind, label]) =>
    uiTemplate`<button type="button" data-clear-filter="${kind}" title="清除该筛选">${escapeHtml(label)} <span aria-hidden="true">×</span></button>`
  ).join('');

  el.querySelectorAll('[data-clear-filter]').forEach(button => button.addEventListener('click', () => {
    const kind = button.dataset.clearFilter;
    if (kind === 'cat') {
      state.cat = '';
      document.querySelectorAll('#cat-seg button').forEach(x => x.classList.toggle('on', x.dataset.cat === ''));
    }
    if (kind === 'filter') {
      state.filter = 'all';
      document.querySelectorAll('.seg button[data-filter]').forEach(x => x.classList.toggle('on', x.dataset.filter === 'all'));
    }
    if (kind === 'tag') state.tag = '';
    state.offset = 0;
    refreshList();
  }));
}

function articleCardHtml(a) {
  const title = (isEnglish() ? a.title : a.title_zh || a.title) || uiText('(无标题)');
  const pinClass = a.pinned ? 'is-pinned' : '';
  const preview = ((isEnglish() ? a.summary : a.summary_zh || a.summary) || '').toString()
    .replace(/https?:\/\/\S+/g, '')
    .replace(/^["“''']+|["”''']+$/g, '')
    .replace(/\s+/g, ' ')
    .trim();
  const ddStatus = a.deep_dive_status;
  const ddBtnLabel = ddStatus === 'ok' ? uiText('查看解读')
    : ddStatus === 'generating' ? uiText('⏳ 生成中…')
    : ddStatus === 'failed' ? uiText('重试解读')
    : uiText('深度解读');
  const ddBusy = ddStatus === 'generating' ? 'is-busy' : '';
  const ddActive = ddStatus === 'ok' ? 'is-done' : '';
  const transBadge = a.translation_status === 'failed'
    ? uiText('<span class="chip chip-trans-fail" title="翻译失败，可点下方按钮重试">⚠️ 翻译失败</span>')
    : a.translation_status === 'ok' ? ''
    : uiText('<span class="chip chip-trans-pending" title="排队等待翻译">待翻译</span>');
  const transAction = a.translation_status === 'ok' ? ''
    : a.translation_status === 'failed'
    ? uiTemplate`<button class="btn-card ghost admin-only" data-action="translate">🔄 重新翻译</button>`
    : uiTemplate`<button class="btn-card ghost admin-only" data-action="translate">🌐 立即翻译</button>`;
  const tagsHtml = (a.tags && a.tags.length)
    ? `<div class="article-tags">${a.tags.slice(0, 2).map(t => `<span class="chip chip-tag" data-tag="${escapeHtml(t)}">${escapeHtml(uiText(t))}</span>`).join('')}</div>`
    : '';
  // Importance badge: only show for clearly high-value items (>=8) to keep signal.
  const impHtml = (typeof a.importance === 'number' && a.importance >= 8)
    ? uiTemplate`<span class="imp-badge" title="重要性 ${a.importance}/10">🔥 ${a.importance}</span>` : '';
  const safeUrl = safeExternalUrl(a.url);
  const originBtn = safeUrl
    ? uiTemplate`<a class="btn-card primary" href="${escapeHtml(safeUrl)}" target="_blank" rel="noopener">原文 ↗</a>` : '';
  const copyBtn = safeUrl ? uiTemplate`<button class="btn-card ghost" data-action="copy">复制链接</button>` : '';
  const handsOn = isEnglish() ? (a.hands_on ? 'Turn this article into a small, verifiable experiment.' : '') : String(a.hands_on || '').trim();
  const expLabel = a.experiment_status === 'completed' ? uiText('✓ 已完成')
    : a.experiment_status ? uiText('查看实验卡') : uiText('生成实验卡');
  const handsOnHtml = handsOn
    ? uiTemplate`<div class="hands-on-box">
        <div><span class="hands-on-label">实践</span>${escapeHtml(handsOn)}</div>
        <div class="hands-on-actions">
          <button class="hands-on-start" data-action="experiment">${expLabel}</button>
          <button class="hands-on-start subtle" data-action="practice">直接问 AI</button>
        </div>
      </div>
      <div class="experiment-slot hidden"></div>` : '';
  const html = uiTemplate`
    <article class="article-card ${pinClass}" data-aid="${escapeHtml(a.id)}">
      <header class="card-head">
        ${catBadge(a.category)}
        ${impHtml}
        <div class="card-titlewrap">
          <h3 class="card-title">${escapeHtml(title)}</h3>
        </div>
        <button class="pin-btn ${a.pinned ? 'on' : ''}" data-action="pin" title="${a.pinned ? uiText('取消收藏') : uiText('收藏')}">${a.pinned ? '★' : '☆'}</button>
      </header>
      <div class="card-meta">
        <span class="meta-src">${escapeHtml(a.source || '')}</span>
        <span class="sep">·</span>
        <span>${fmtDate(a.date)}</span>
        ${transBadge}
      </div>
      ${preview ? `<div class="card-preview">${escapeHtml(preview)}</div>` : ''}
      ${handsOnHtml}
      ${tagsHtml}
      <div class="card-actions">
        ${originBtn}
        <button class="btn-card ${ddActive ? 'success' : 'accent'} ${ddBusy}" data-action="dive">${ddBtnLabel}</button>
        <details class="card-more">
          <summary>更多</summary>
          <div class="card-more-menu">
            ${copyBtn}
            <button class="btn-card ghost" data-action="ask" title="带这篇上下文问 AI 助手">问 AI</button>
            <button class="btn-card ghost" data-action="srs" title="加入间隔复习库">加入知识卡</button>
            ${transAction}
          </div>
        </details>
      </div>
    </article>`;
  return html.replace("</article>", learningLinks(a) + "</article>");
}

export function renderList() {
  const listEl = $('#article-list');
  if (!state.items.length) {
    listEl.innerHTML = uiText('<div class="muted-card" style="padding:48px 16px;text-align:center">📭 这一页没有内容</div>');
    return;
  }
  listEl.innerHTML = state.items.map(articleCardHtml).join('');

  // Tag chips → filter the feed by that tag (toggle off if already active).
  listEl.querySelectorAll('[data-tag]').forEach(chip =>
    chip.addEventListener('click', (e) => {
      e.stopPropagation();
      const t = chip.dataset.tag;
      state.tag = state.tag === t ? '' : t;
      state.offset = 0;
      refreshList();
    }));

  listEl.querySelectorAll('.article-card').forEach(el => {
    const aid = el.dataset.aid;
    el.querySelector('[data-action="dive"]')?.addEventListener('click', () => {
      const a = state.items.find(x => x.id === aid);
      const generate = a?.deep_dive_status !== 'ok';
      jumpToDive(aid, { generate });
    });
    el.querySelector('[data-action="pin"]')?.addEventListener('click', () => togglePin(aid));
    el.querySelector('[data-action="ask"]')?.addEventListener('click', () => {
      const a = state.items.find(x => x.id === aid);
      askAboutArticle(a);
    });
    el.querySelector('[data-action="practice"]')?.addEventListener('click', () => {
      const a = state.items.find(x => x.id === aid);
      practiceArticle(a);
    });
    el.querySelector('[data-action="experiment"]')?.addEventListener('click', (event) => {
      const a = state.items.find(x => x.id === aid);
      toggleExperiment(a, el.querySelector('.experiment-slot'), event.currentTarget);
    });
    el.querySelector('[data-action="srs"]')?.addEventListener('click', async (e) => {
      const btn = e.currentTarget, orig = btn.textContent; btn.disabled = true; btn.textContent = uiText('⏳ 加入中…');
      try {
        await api('POST', '/api/ai-news/review/cards', { source_type: 'article', source_id: aid });
        btn.textContent = uiText('✓ 已加入'); btn.classList.add('success');
      } catch (err) {
        btn.textContent = err.status === 409 ? uiText('✓ 已在库') : uiText('❌ 失败');
        if (err.status !== 409) alert(uiText('加入复习失败：') + err.message);
        setTimeout(() => { btn.disabled = false; btn.textContent = orig; btn.classList.remove('success'); }, 1600);
      }
    });
    el.querySelector('[data-action="copy"]')?.addEventListener('click', (e) => {
      e.preventDefault();
      const a = state.items.find(x => x.id === aid);
      if (a?.url) {
        navigator.clipboard.writeText(a.url).then(() => {
          const btn = e.currentTarget, orig = btn.textContent;
          btn.textContent = uiText('✓ 已复制'); btn.classList.add('flash');
          setTimeout(() => { btn.textContent = orig; btn.classList.remove('flash'); }, 1400);
        });
      }
    });
    el.querySelector('[data-action="translate"]')?.addEventListener('click', async (e) => {
      const btn = e.currentTarget; const orig = btn.textContent; btn.disabled = true; btn.textContent = uiText('🌐 翻译中…');
      try {
        await api('POST', `/api/ai-news/articles/${aid}/retranslate`);
        await refreshList();
      } catch (err) {
        alert(uiText('翻译失败：') + err.message);
        btn.disabled = false; btn.textContent = orig;
      }
    });
  });
}

// Open the chat agent pre-loaded with this article's context, so the user can
// ask about the specific piece without retyping what it is. (Scene-embedded
// agent — same mechanism the reflection "展开聊" uses.)
function askAboutArticle(a) {
  if (!a) return;
  if (!isAuthed()) { openAuthModal(uiText('登录后即可用 AI 助手就这篇提问')); return; }
  const chat = window.__sparrowChat;
  if (!chat) { alert(uiText('AI 助手未就绪')); return; }
  const title = (isEnglish() ? a.title : a.title_zh || a.title) || uiText('(无标题)');
  const prompt = uiTemplate`关于这篇文章：《${title}》${a.url ? '（' + a.url + '）' : ''}\n我想了解：`;
  chat.toggle(true);
  chat.input.value = prompt;
  chat.input.focus();
  // Move caret to end so the user just continues typing their question.
  const len = chat.input.value.length;
  try { chat.input.setSelectionRange(len, len); } catch (e) { /* ignore */ }
}

function practiceArticle(a) {
  if (!a) return;
  if (!isAuthed()) { openAuthModal(uiText('登录后即可让 AI 助手带你实践')); return; }
  const chat = window.__sparrowChat;
  if (!chat) { alert(uiText('AI 助手未就绪')); return; }
  const title = (isEnglish() ? a.title : a.title_zh || a.title) || uiText('(无标题)');
  const step = String(a.hands_on || '').trim();
  chat.toggle(true);
  chat.input.value = uiTemplate`我想实践这篇文章：《${title}》${a.url ? `（${a.url}）` : ''}\n建议起点：${step}\n请先核对原文，再给我一个 15 分钟内能完成的最小实践方案；明确前置条件、步骤和验证结果，不要编造命令或 API。`;
  chat.input.focus();
  const len = chat.input.value.length;
  try { chat.input.setSelectionRange(len, len); } catch (e) { /* ignore */ }
}

export function renderPageNav() {
  const start = state.total === 0 ? 0 : state.offset + 1;
  const end = Math.min(state.offset + state.limit, state.total);
  $('#page-info').textContent = state.total ? `${start}–${end} / ${state.total}` : '0 / 0';
  $('#btn-prev').disabled = state.offset <= 0;
  $('#btn-next').disabled = state.offset + state.limit >= state.total;
}

export async function togglePin(aid) {
  try {
    const r = await api('POST', `/api/ai-news/articles/${aid}/pin`);
    const a = state.items.find(x => x.id === aid);
    if (a) a.pinned = r.pinned;
    renderList();
  } catch (e) { alert(uiText('收藏失败：') + e.message); }
}
