// Secondary views: today's summary, source health.
import { $, $$, escapeHtml, fmtDate, catBadge, safeExternalUrl } from './util.js';
import { api, renderMermaidInside } from './api.js';
import { getUser } from './auth.js';
import { renderMarkdown } from './markdown.js';

// ── Today's summary ──────────────────────────────────────────────────
function linkSummaryCitations(root, cohort = []) {
  if (!root || !cohort.length) return;

  const references = new Map();
  cohort.forEach((article, index) => {
    try {
      const url = safeExternalUrl(article.url);
      if (!url) return;
      references.set(index + 1, { ...article, url });
    } catch (e) { /* Ignore missing or malformed source URLs. */ }
  });
  if (!references.size) return;

  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const textNodes = [];
  while (walker.nextNode()) textNodes.push(walker.currentNode);

  textNodes.forEach(node => {
    if (node.parentElement?.closest('a, code, pre, script, style')) return;
    const text = node.textContent || '';
    const matches = [...text.matchAll(/\[(\d+)\]/g)]
      .filter(match => references.has(Number(match[1])));
    if (!matches.length) return;

    const fragment = document.createDocumentFragment();
    let cursor = 0;
    matches.forEach(match => {
      const article = references.get(Number(match[1]));
      fragment.append(document.createTextNode(text.slice(cursor, match.index)));

      const link = document.createElement('a');
      link.className = 'summary-citation';
      link.href = article.url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = match[0];
      const label = article.title || article.source || `引用 ${match[1]}`;
      link.title = `打开原文：${label}`;
      link.setAttribute('aria-label', `引用 ${match[1]}，打开原文：${label}`);
      fragment.append(link);
      cursor = match.index + match[0].length;
    });
    fragment.append(document.createTextNode(text.slice(cursor)));
    node.replaceWith(fragment);
  });
}

function collapseSecondarySummary(root) {
  const heading = [...root.querySelectorAll('h1, h2, h3')]
    .find(node => node.parentElement === root && ['边角料', '更多动态'].includes(node.textContent.trim()));
  if (!heading) return;

  const details = document.createElement('details');
  details.className = 'summary-more';
  const toggle = document.createElement('summary');
  const label = document.createElement('span');
  label.textContent = '更多动态';
  const content = document.createElement('div');
  content.className = 'summary-more-content';
  toggle.append(label);
  details.append(toggle, content);
  heading.replaceWith(details);

  while (details.nextSibling) content.append(details.nextSibling);
  const count = content.querySelectorAll('li').length;
  if (count) {
    const meta = document.createElement('small');
    meta.textContent = `${count} 条`;
    toggle.append(meta);
  }
}

async function renderSummary(body, summary) {
  body.innerHTML = renderMarkdown(summary.body || '');
  linkSummaryCitations(body, summary.cohort || []);
  collapseSecondarySummary(body);
  await renderMermaidInside(body);
}

function renderBreaking(items = []) {
  const section = $('#breaking-section'), list = $('#breaking-list');
  if (!section || !list) return;
  if (!items.length) {
    section.classList.add('hidden');
    list.innerHTML = '';
    return;
  }
  list.innerHTML = items.map(item => {
    const safeUrl = safeExternalUrl(item.url);
    const title = escapeHtml(item.title || '（无标题）');
    const linkedTitle = safeUrl
      ? `<a href="${escapeHtml(safeUrl)}" target="_blank" rel="noopener">${title} ↗</a>`
      : title;
    return `<article class="breaking-item ${item.severity === 'critical' ? 'is-critical' : ''}">
      <div class="breaking-meta">
        <span class="breaking-label">${escapeHtml(item.label || '重要更新')}</span>
        <span>${escapeHtml(item.source || '')}</span>
        <time>${item.date ? fmtDate(item.date) : ''}</time>
      </div>
      <div class="breaking-title">${linkedTitle}</div>
      <div class="breaking-reason">${escapeHtml(item.reason || '')}</div>
    </article>`;
  }).join('');
  section.classList.remove('hidden');
}

export async function loadSummary() {
  const meta = $('#summary-meta'), body = $('#summary-body'), cohort = $('#summary-cohort');
  body.innerHTML = '<div class="muted-card">加载中…</div>';
  try {
    const r = await api('GET', '/api/ai-news/summary/today');
    renderBreaking(r.breaking_items || []);
    const s = r.summary;
    cohort.textContent = r.cohort_size
      ? `基于今日 ${r.cohort_size} 篇文章 · 日期 ${r.today || ''}` : `今日候选 0 篇`;
    if (s && s.body) {
      meta.textContent = s.generated_at ? '生成于 ' + fmtDate(s.generated_at) : '';
      await renderSummary(body, s);
    } else {
      meta.textContent = '';
      body.innerHTML = `<div class="muted-card" style="padding:32px 20px">
        ✨ 还没有生成今日速报<br>
        <span class="text-faint" style="font-size:12px">点击右上「重新生成」按钮，会基于最近 24h 候选文章（共 ${r.cohort_size || 0} 篇）调 LLM 生成一份。</span>
      </div>`;
    }
  } catch (e) {
    renderBreaking([]);
    body.innerHTML = '<div class="muted-card">❌ ' + escapeHtml(e.message) + '</div>';
  }
}

export async function regenSummary() {
  const body = $('#summary-body');
  body.innerHTML = '<div class="muted-card">⏳ 重新生成中（约 20-30s）…</div>';
  try {
    const r = await api('POST', '/api/ai-news/summary/today');
    const s = r.summary || {};
    await renderSummary(body, s);
    $('#summary-meta').textContent = '生成于刚才';
    $('#summary-cohort').textContent = s.cohort_size ? `基于今日 ${s.cohort_size} 篇文章` : '';
  } catch (e) {
    body.innerHTML = '<div class="muted-card">❌ ' + escapeHtml(e.message) + '</div>';
  }
}

// ── For-you (personalized today ranking) ─────────────────────────────
export async function loadForYou() {
  const body = $('#foryou-body'), meta = $('#foryou-meta');
  body.innerHTML = '<div class="muted-card">加载中…</div>';
  try {
    const r = await api('GET', '/api/ai-news/for-you?limit=20');
    const items = r.items || [];
    if (r.personalized) {
      meta.textContent = `今日候选 ${r.today_count} 篇 · 已按你的关注排序`;
    } else {
      meta.innerHTML = '<span class="text-faint">收藏文章 / 与助手对话后，这里会按你的兴趣排序</span>';
    }
    if (!items.length) {
      body.innerHTML = '<div class="muted-card" style="padding:32px 20px">📭 今日还没有候选文章</div>';
      return;
    }
    body.innerHTML = items.map(forYouCard).join('');
  } catch (e) {
    body.innerHTML = '<div class="muted-card">❌ ' + escapeHtml(e.message) + '</div>';
  }
}

function forYouCard(a) {
  const title = a.title_zh || a.title || '(无标题)';
  const reasons = (a._reasons && a._reasons.length)
    ? `<div class="fy-reasons">${a._reasons.map(r => `<span class="chip chip-tag">${escapeHtml(r)}</span>`).join('')}</div>`
    : '';
  const safeUrl = safeExternalUrl(a.url);
  const link = safeUrl
    ? `<a href="${escapeHtml(safeUrl)}" target="_blank" rel="noopener">${escapeHtml(title)} ↗</a>`
    : escapeHtml(title);
  return `
    <div class="fy-item">
      <div class="fy-head">
        ${catBadge(a.category)}
        <span class="fy-src text-faint">${escapeHtml(a.source || '')}</span>
        <span class="fy-date text-faint">${a.date ? fmtDate(a.date) : ''}</span>
      </div>
      <div class="fy-title">${link}</div>
      ${reasons}
    </div>`;
}

// ── Personal profile ─────────────────────────────────────────────────
export async function loadProfile() {
  const meta = $('#profile-meta'), body = $('#profile-body');
  body.innerHTML = '<div class="muted-card">加载中…</div>';
  try {
    const r = await api('GET', '/api/ai-news/profile');
    if (r.status === 'ok' && r.body) {
      meta.textContent = r.generated_at ? '生成于 ' + fmtDate(r.generated_at) : '';
      body.innerHTML = renderMarkdown(r.body);
    } else {
      meta.textContent = '';
      body.innerHTML = `<div class="muted-card" style="padding:32px 20px">
        🪪 还没有生成画像<br>
        <span class="text-faint" style="font-size:12px">点右上「生成 / 更新画像」，会聚合你的收藏 / 深度解读 / 追踪主题 / 对话，调 LLM 生成。先 pin 几篇或聊几句效果更好。</span>
      </div>`;
    }
  } catch (e) {
    body.innerHTML = '<div class="muted-card">❌ ' + escapeHtml(e.message) + '</div>';
  }
}

export async function regenProfile() {
  const body = $('#profile-body');
  body.innerHTML = '<div class="muted-card">⏳ 生成中（约 15-25s）…</div>';
  try {
    const r = await api('POST', '/api/ai-news/profile');
    body.innerHTML = renderMarkdown(r.body || '');
    $('#profile-meta').textContent = '生成于刚才';
  } catch (e) {
    body.innerHTML = '<div class="muted-card">❌ ' + escapeHtml(e.message) + '</div>';
  }
}

// ── Source health ────────────────────────────────────────────────────
const SRC_CAT_LABELS = {
  vendor: '🏢 厂商官方', blog: '✍️ 专家博客', expert: '🧠 专家观点', media: '📰 科技媒体',
  paper: '📄 学术论文', 'x-ai': '𝕏 大 V', trending: '📈 GitHub Trending', community: '💬 社区', other: '其他',
};
const SRC_ORDER = ['vendor', 'blog', 'expert', 'media', 'paper', 'x-ai', 'trending', 'community'];

export async function loadSources() {
  try {
    const candidateRequest = getUser()?.role === 'admin'
      ? api('GET', '/api/ai-news/quality/benchmark-candidates').catch(() => null)
      : Promise.resolve(null);
    const [r, quality, candidates] = await Promise.all([
      api('GET', '/api/ai-news/sources'),
      api('GET', '/api/ai-news/quality/report').catch(() => null),
      candidateRequest,
    ]);
    renderQualityReport(quality, candidates);
    $('#cnt-sources').textContent = r.length;
    const groups = {};
    for (const s of r) (groups[s.category || 'other'] = groups[s.category || 'other'] || []).push(s);

    const okN = r.filter(s => s.health_status === 'healthy').length;
    const errN = r.filter(s => s.health_status === 'error').length;
    const staleN = r.filter(s => s.health_status === 'stale').length;
    const neverN = r.filter(s => s.health_status === 'never').length;
    const attention = r.filter(s => ['error', 'stale'].includes(s.health_status));
    const totalArticles = r.reduce((a, s) => a + (s.article_count || 0), 0);
    const healthBar = `
      <div class="src-health">
        <div class="src-health-stats">
          <span class="hs-ok">✓ ${okN} 正常</span>
          ${errN ? `<span class="hs-err">⚠ ${errN} 抓取失败</span>` : ''}
          ${staleN ? `<span class="hs-warn">◷ ${staleN} 调度过期</span>` : ''}
          ${neverN ? `<span class="hs-neutral">⊝ ${neverN} 未抓取</span>` : ''}
          <span class="hs-neutral">· 共 ${r.length} 源 · 当前库 ${totalArticles} 篇</span>
        </div>
        ${attention.length ? `<div class="src-attention"><strong>需关注：</strong>${attention.slice(0, 8).map(s => `${escapeHtml(s.name)}（${escapeHtml(s.health_reason || '异常')}）`).join('、')}${attention.length > 8 ? ` 等 ${attention.length} 个源` : ''}</div>` : ''}
      </div>`;

    const healthRank = { error: 0, stale: 1, never: 2, healthy: 3 };
    Object.values(groups).forEach(items => items.sort((a, b) =>
      (healthRank[a.health_status] ?? 9) - (healthRank[b.health_status] ?? 9)
      || String(a.name || '').localeCompare(String(b.name || ''))));
    const cats = SRC_ORDER.concat(Object.keys(groups).filter(k => !SRC_ORDER.includes(k)));
    const html = healthBar + cats.map(cat => {
      const items = groups[cat];
      if (!items) return '';
      return `
        <div class="src-group">
          <div class="src-group-head">${SRC_CAT_LABELS[cat] || cat} <span class="text-faint">· ${items.length}</span></div>
          <div class="src-grid">${items.map(sourceCard).join('')}</div>
        </div>`;
    }).join('');
    $('#sources-list').innerHTML = html;
  } catch (e) {
    renderQualityReport(null);
    $('#sources-list').innerHTML = '<div class="muted-card">❌ ' + escapeHtml(e.message) + '</div>';
  }
}

function pct(value) {
  return value == null ? '—' : `${Math.round(value * 100)}%`;
}

function renderQualityReport(report, candidates = null) {
  const root = $('#quality-report');
  if (!root) return;
  if (!report) {
    root.innerHTML = '';
    return;
  }
  const source = report.source_health || {};
  const content = report.content_coverage || {};
  const pipeline = report.pipeline || {};
  const value = report.source_value || {};
  const benchmark = report.benchmark_coverage || {};
  const statusLabel = { healthy: '正常', watch: '需关注', critical: '有缺口' }[report.status] || '未知';
  const latency = pipeline.latency_sample_size
    ? `${pipeline.median_discovery_minutes ?? '—'} / ${pipeline.p90_discovery_minutes ?? '—'} 分钟`
    : '等待新入库样本';
  root.innerHTML = `<section class="quality-card is-${escapeHtml(report.status || 'unknown')}">
    <div class="quality-head"><strong>覆盖质量体检</strong><span>${escapeHtml(statusLabel)} · 最近 ${report.window_hours || 30} 小时</span></div>
    <div class="quality-metrics">
      <div><b>${pct(source.fast_rate)}</b><span>高时效源健康</span></div>
      <div><b>${pct(content.visible_rate)}</b><span>高影响事件露出</span></div>
      <div><b>${pipeline.pending_enrichment ?? 0}</b><span>待翻译 / 评分</span></div>
      <div><b>${escapeHtml(latency)}</b><span>发现延迟 P50 / P90</span></div>
      <div><b>${value.high_value_sources ?? 0}</b><span>高价值源（${value.window_days || 30} 天）</span></div>
      <div><b>${pct(benchmark.on_time_recall_rate)}</b><span>必达事件准时召回</span></div>
    </div>
    <div class="quality-findings">${(report.findings || []).map(item =>
      `<div class="qf-${escapeHtml(item.level || '')}"><b>${escapeHtml(item.title || '')}</b><span>${escapeHtml(item.detail || '')}</span></div>`
    ).join('')}</div>
    ${renderSourceValue(value)}
    ${renderBenchmarkCoverage(benchmark, candidates)}
  </section>`;
  bindBenchmarkControls(root, candidates?.items || []);
}

function renderSourceValue(value) {
  const top = value.top_sources || [];
  const review = value.review_candidates || [];
  if (!top.length) {
    return `<div class="source-value-empty">来源价值评分等待更多样本（当前滚动库 ${value.sample_articles || 0} 篇、覆盖 ${value.observed_span_days ?? 0} 天；每源至少需要 3 个不同事件）。</div>`;
  }
  const topRows = top.slice(0, 6).map(item => {
    const detail = `${item.event_count || 0} 个事件 · 独家 ${item.exclusive_events || 0} · 首发现 ${item.first_seen_events || 0}`;
    return `<span class="source-value-chip" title="${escapeHtml(detail)}"><b>${escapeHtml(item.name || '')}</b><em>${item.score ?? '—'}</em></span>`;
  }).join('');
  const reviewRow = review.length
    ? `<div class="source-review"><b>待复核低信号源</b><span>${review.map(item => {
      const repeated = item.duplicate_rate == null ? '—' : `${Math.round(item.duplicate_rate * 100)}%`;
      return `${escapeHtml(item.name || '')}（${item.score} 分，重复 ${repeated}）`;
    }).join('、')}</span></div>`
    : '';
  return `<div class="source-value">
    <div class="source-value-head"><b>近 ${value.window_days || 30} 天来源贡献</b><span>滚动库 ${value.sample_articles || 0} 篇 / 覆盖 ${value.observed_span_days ?? 0} 天 · 已评估 ${value.evaluated_sources || 0} · 样本不足 ${value.insufficient_sources || 0}</span></div>
    <div class="source-value-list">${topRows}</div>
    ${reviewRow}
  </div>`;
}

function renderBenchmarkCoverage(benchmark, candidates) {
  const items = benchmark.items || [];
  const issues = items.filter(item => ['missed', 'late', 'pending'].includes(item.status)).slice(0, 6);
  const labels = { on_time: '准时', late: '迟到', missed: '漏报', pending: '观察中' };
  const issueRows = issues.length
    ? `<div class="benchmark-issues">${issues.map(item => {
      const sourceUrl = safeExternalUrl(item.source_url);
      const title = sourceUrl
        ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener">${escapeHtml(item.title || '')}</a>`
        : escapeHtml(item.title || '');
      return `<div class="benchmark-row is-${escapeHtml(item.status || '')}"><span>${labels[item.status] || item.status}</span><b>${title}</b><small>${escapeHtml(fmtDate(item.occurred_at))}</small></div>`;
    }).join('')}</div>`
    : `<div class="source-value-empty">${items.length ? '当前必达事件均已准时命中。' : '尚未登记必达事件；管理员可添加真实事件作为漏报基准。'}</div>`;
  const adminRows = items.slice(0, 10).map(item =>
    `<div class="benchmark-admin-row"><span>${labels[item.status] || item.status} · ${escapeHtml(item.title || '')}</span><button class="ghost sm" data-benchmark-delete="${escapeHtml(item.id || '')}">删除</button></div>`
  ).join('');
  const candidateItems = candidates?.items || [];
  const candidateRows = candidateItems.map((item, index) => {
    const sourceUrl = safeExternalUrl(item.source_url);
    const title = sourceUrl
      ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener">${escapeHtml(item.title || '')}</a>`
      : escapeHtml(item.title || '');
    return `<div class="benchmark-candidate-row">
      <span>${escapeHtml(item.label || '候选')}</span>
      <div><b>${title}</b><small>${escapeHtml(item.reason || '')} · ${escapeHtml(item.source || '')} · ${escapeHtml(fmtDate(item.occurred_at))} · 发现用时 ${item.discovery_minutes ?? '—'} 分钟</small></div>
      <button class="ghost sm" data-benchmark-candidate="${index}">加入基准</button>
    </div>`;
  }).join('');
  return `<div class="benchmark-panel">
    <div class="source-value-head"><b>必达事件基准</b><span>近 ${benchmark.window_days || 30} 天 · 准时 ${benchmark.on_time || 0} / 迟到 ${benchmark.late || 0} / 漏报 ${benchmark.missed || 0} / 观察中 ${benchmark.pending || 0}</span></div>
    ${issueRows}
    <div class="benchmark-admin admin-only">
      <div class="benchmark-candidates">
        <div class="source-value-head"><b>自动发现候选（${candidateItems.length}）</b><span>近 ${candidates?.window_days || 7} 天官方高影响事件 · 人工确认后才计入召回率</span></div>
        ${candidateRows || '<div class="source-value-empty">暂无未登记候选。</div>'}
      </div>
      <div class="benchmark-form">
        <input id="benchmark-title" maxlength="200" placeholder="事件标题，如：GPT-6 正式发布" />
        <input id="benchmark-time" type="datetime-local" title="事件发生时间" />
        <input id="benchmark-terms" maxlength="400" placeholder="匹配词，逗号分隔，如：GPT-6, OpenAI" />
        <input id="benchmark-url" type="url" maxlength="500" placeholder="官方来源链接（可选）" />
        <select id="benchmark-deadline" title="最长发现时间">
          <option value="6">6 小时内</option><option value="12">12 小时内</option>
          <option value="24" selected>24 小时内</option><option value="48">48 小时内</option>
        </select>
        <button class="primary sm" id="benchmark-add">登记必达事件</button>
      </div>
      <div id="benchmark-msg" class="text-xs text-faint"></div>
      ${adminRows ? `<div class="benchmark-admin-list">${adminRows}</div>` : ''}
    </div>
  </div>`;
}

function bindBenchmarkControls(root, candidates = []) {
  const timeInput = root.querySelector('#benchmark-time');
  if (timeInput && !timeInput.value) {
    const local = new Date(Date.now() - new Date().getTimezoneOffset() * 60000);
    timeInput.value = local.toISOString().slice(0, 16);
  }
  root.querySelector('#benchmark-add')?.addEventListener('click', async (event) => {
    const button = event.currentTarget;
    const msg = root.querySelector('#benchmark-msg');
    const title = root.querySelector('#benchmark-title')?.value.trim() || '';
    const occurredValue = timeInput?.value || '';
    const matchTerms = (root.querySelector('#benchmark-terms')?.value || '')
      .split(/[,，\n]/).map(term => term.trim()).filter(Boolean);
    if (!title || !occurredValue || (!matchTerms.length && !root.querySelector('#benchmark-url')?.value.trim())) {
      msg.textContent = '请填写标题、事件时间，并至少提供匹配词或官方链接。';
      return;
    }
    button.disabled = true;
    msg.textContent = '正在登记…';
    try {
      await api('POST', '/api/ai-news/quality/benchmarks', {
        title,
        occurred_at: new Date(occurredValue).toISOString(),
        source_url: root.querySelector('#benchmark-url')?.value.trim() || '',
        match_terms: matchTerms,
        deadline_hours: Number(root.querySelector('#benchmark-deadline')?.value || 24),
      });
      await loadSources();
    } catch (error) {
      msg.textContent = error.message || '登记失败';
      button.disabled = false;
    }
  });
  root.querySelectorAll('[data-benchmark-delete]').forEach(button => button.addEventListener('click', async () => {
    if (!window.confirm('删除这个必达事件基准？')) return;
    button.disabled = true;
    try {
      await api('DELETE', `/api/ai-news/quality/benchmarks/${encodeURIComponent(button.dataset.benchmarkDelete)}`);
      await loadSources();
    } catch (error) {
      const msg = root.querySelector('#benchmark-msg');
      if (msg) msg.textContent = error.message || '删除失败';
      button.disabled = false;
    }
  }));
  root.querySelectorAll('[data-benchmark-candidate]').forEach(button => button.addEventListener('click', async () => {
    const item = candidates[Number(button.dataset.benchmarkCandidate)];
    if (!item) return;
    const msg = root.querySelector('#benchmark-msg');
    button.disabled = true;
    if (msg) msg.textContent = `正在登记「${item.title}」…`;
    try {
      await api('POST', '/api/ai-news/quality/benchmarks', {
        title: item.title,
        occurred_at: item.occurred_at,
        source_url: item.source_url,
        event_key: item.event_key,
        match_terms: item.match_terms || [],
        deadline_hours: item.deadline_hours,
      });
      await loadSources();
    } catch (error) {
      if (msg) msg.textContent = error.message || '登记失败';
      button.disabled = false;
    }
  }));
}

function sourceCard(s) {
  let status, statusClass;
  if (s.health_status === 'error') { status = '⚠️ 抓取失败'; statusClass = 'st-err'; }
  else if (s.health_status === 'stale') { status = '◷ 调度过期'; statusClass = 'st-stale'; }
  else if (s.health_status === 'healthy') { status = '✓ 正常'; statusClass = 'st-ok'; }
  else { status = '⊝ 尚未抓取'; statusClass = 'st-neutral'; }
  const healthDetail = ['error', 'stale'].includes(s.health_status)
    ? `<div class="src-err ${s.health_status === 'stale' ? 'is-stale' : ''}" title="${escapeHtml(s.last_error || s.health_reason || '')}">${escapeHtml(s.last_error ? (s.last_error.length > 80 ? s.last_error.slice(0, 77) + '…' : s.last_error) : s.health_reason || '')}</div>`
    : '';
  const lastFetch = s.last_fetch ? fmtDate(s.last_fetch) : '—';
  const lastOk = s.last_ok ? fmtDate(s.last_ok) : '—';
  const newestArticle = s.newest_article_at ? fmtDate(s.newest_article_at) : '—';
  const desc = s.description ? escapeHtml(s.description) : '<span class="text-faint">（无简介）</span>';
  const cadence = { fast: '每小时', standard: '每 4 小时', slow: '每 12 小时' }[s.cadence] || '';
  const host = s.url ? (s.url.replace(/^https?:\/\//, '').split('/')[0] || '') : '';
  const safeUrl = safeExternalUrl(s.url);
  const linkRow = safeUrl
    ? `<a class="src-link" href="${escapeHtml(safeUrl)}" target="_blank" rel="noopener" title="RSS 订阅地址">${escapeHtml(host)} ↗</a>`
    : '<span class="text-faint">（无 URL）</span>';
  return `
    <div class="src-card">
      <div class="src-card-head">
        ${catBadge(s.category)}
        <div class="src-name">${escapeHtml(s.name)}</div>
        <span class="src-status ${statusClass}">${status}</span>
      </div>
      <div class="src-desc">${desc}</div>
      ${healthDetail}
      <div class="src-stats">
        ${cadence ? `<span title="自动抓取频率">↻ ${cadence}</span><span class="dot-sep">·</span>` : ''}
        <span title="本次入库 / 被过滤"><span class="hs-ok">+${s.last_added ?? 0}</span> <span class="text-faint">/ ${s.last_filtered ?? 0} 过滤</span></span>
        ${(s.last_invalid_date || 0) > 0 ? `<span class="dot-sep">·</span><span class="hs-err" title="发布日期缺失或异常，未入库">日期异常 ${s.last_invalid_date} 条</span>` : ''}
        <span class="dot-sep">·</span>
        <span title="当前滚动文章库中的数量">📚 ${s.article_count || 0} 篇</span>
        <span class="dot-sep">·</span>
        <span title="最近抓取">⏱ ${lastFetch}</span>
        ${s.consecutive_failures ? `<span class="dot-sep">·</span><span class="hs-err">连续失败 ${s.consecutive_failures} 次</span>` : ''}
      </div>
      <div class="src-stats text-faint"><span title="最近成功抓取">成功 ${lastOk}</span><span class="dot-sep">·</span><span title="当前库中该来源最新文章">最新内容 ${newestArticle}</span></div>
      <div class="src-foot">${linkRow}</div>
    </div>`;
}
