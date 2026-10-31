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
    const benchmarkRequest = getUser()?.role === 'admin'
      ? api('GET', '/api/ai-news/quality/benchmarks').catch(() => null)
      : Promise.resolve(null);
    const [r, quality, candidates, benchmarks] = await Promise.all([
      api('GET', '/api/ai-news/sources'),
      api('GET', '/api/ai-news/quality/report').catch(() => null),
      candidateRequest,
      benchmarkRequest,
    ]);
    renderQualityReport(quality, candidates, benchmarks);
    $('#cnt-sources').textContent = r.length;
    const groups = {};
    for (const s of r) (groups[s.category || 'other'] = groups[s.category || 'other'] || []).push(s);

    const okN = r.filter(s => s.health_status === 'healthy').length;
    const errN = r.filter(s => s.health_status === 'error').length;
    const staleN = r.filter(s => s.health_status === 'stale').length;
    const neverN = r.filter(s => s.health_status === 'never').length;
    const disabledN = r.filter(s => s.health_status === 'disabled').length;
    const quietN = r.filter(s => s.enabled !== false && s.content_status === 'quiet').length;
    const dormantN = r.filter(s => s.enabled !== false && s.content_status === 'dormant').length;
    const attention = r.filter(s =>
      s.enabled !== false && (['error', 'stale'].includes(s.health_status) || s.content_status === 'dormant'));
    const totalArticles = r.reduce((a, s) => a + (s.article_count || 0), 0);
    const healthBar = `
      <div class="src-health">
        <div class="src-health-stats">
          <span class="hs-ok">✓ ${okN} 正常</span>
          ${errN ? `<span class="hs-err">⚠ ${errN} 抓取失败</span>` : ''}
          ${staleN ? `<span class="hs-warn">◷ ${staleN} 调度过期</span>` : ''}
          ${neverN ? `<span class="hs-neutral">⊝ ${neverN} 未抓取</span>` : ''}
          ${disabledN ? `<span class="hs-neutral">⏸ ${disabledN} 已停用</span>` : ''}
          ${dormantN ? `<span class="hs-err">◌ ${dormantN} 疑似停更</span>` : ''}
          ${quietN ? `<span class="hs-warn">◌ ${quietN} 内容偏久</span>` : ''}
          <span class="hs-neutral">· ${r.length - disabledN} 个启用 / 共 ${r.length} 源 · 当前库 ${totalArticles} 篇</span>
        </div>
        ${attention.length ? `<div class="src-attention"><strong>需关注：</strong>${attention.slice(0, 8).map(s => `${escapeHtml(s.name)}（${escapeHtml(['error', 'stale'].includes(s.health_status) ? (s.health_reason || '异常') : (s.content_reason || '内容疑似停更'))}）`).join('、')}${attention.length > 8 ? ` 等 ${attention.length} 个源` : ''}</div>` : ''}
      </div>`;

    const healthRank = { error: 0, stale: 1, never: 2, healthy: 3, disabled: 4 };
    Object.values(groups).forEach(items => items.sort((a, b) =>
      (healthRank[a.health_status] ?? 9) - (healthRank[b.health_status] ?? 9)
      || Number(b.content_status === 'dormant') - Number(a.content_status === 'dormant')
      || Number(b.content_status === 'quiet') - Number(a.content_status === 'quiet')
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
    bindSourceControls($('#sources-list'));
  } catch (e) {
    renderQualityReport(null);
    $('#sources-list').innerHTML = '<div class="muted-card">❌ ' + escapeHtml(e.message) + '</div>';
  }
}

function pct(value) {
  return value == null ? '—' : `${Math.round(value * 100)}%`;
}

function renderQualityReport(report, candidates = null, benchmarks = null) {
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
  const noise = report.source_noise || {};
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
    ${renderSourceNoise(noise)}
    ${renderBenchmarkCoverage(benchmark, candidates, benchmarks)}
  </section>`;
  bindBenchmarkControls(root, candidates?.items || []);
}

function renderSourceNoise(noise) {
  const items = noise.noisiest_sources || [];
  if (!noise.sampled_sources) {
    return '<div class="source-value-empty">来源噪声率等待成功抓取样本。</div>';
  }
  const chips = items.slice(0, 6).map(item => {
    const detail = `${item.samples || 0} 轮 · 接受 ${item.accepted || 0} · 过滤 ${item.filtered || 0} · 日期异常 ${item.invalid_date || 0}`;
    return `<span class="source-value-chip source-noise-chip" title="${escapeHtml(detail)}"><b>${escapeHtml(item.name || '')}</b><em>${pct(item.noise_rate)}</em></span>`;
  }).join('');
  const warning = (noise.possible_overfilter || []).length
    ? `<div class="source-review"><b>可能过滤过严</b><span>${noise.possible_overfilter.map(item => `${escapeHtml(item.name || '')}（${item.filtered || 0} 条全被过滤）`).join('、')}</span></div>`
    : '';
  return `<div class="source-value source-noise">
    <div class="source-value-head"><b>近 ${noise.window_days || 7} 天来源噪声</b><span>${noise.sampled_sources || 0} 个来源 / ${noise.sample_count || 0} 轮 · 解析 ${noise.parsed || 0} · 内容过滤 ${noise.filtered || 0}（${pct(noise.noise_rate)}）· 日期异常 ${noise.invalid_date || 0}</span></div>
    ${chips ? `<div class="source-value-list">${chips}</div>` : '<div class="source-value-empty">当前样本没有内容过滤记录。</div>'}
    ${warning}
  </div>`;
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

function renderBenchmarkCoverage(benchmark, candidates, benchmarks) {
  const items = benchmark.items || [];
  const adminById = new Map((benchmarks?.items || []).map(item => [item.id, item]));
  const issues = items.filter(item => ['missed', 'late', 'pending'].includes(item.status)).slice(0, 6);
  const labels = { on_time: '准时', late: '迟到', missed: '漏报', pending: '观察中' };
  const issueRows = issues.length
    ? `<div class="benchmark-issues">${issues.map(item => {
      const sourceUrl = safeExternalUrl(item.source_url);
      const title = sourceUrl
        ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener">${escapeHtml(item.title || '')}</a>`
        : escapeHtml(item.title || '');
      const adminItem = adminById.get(item.id);
      const itemWithAdminState = adminItem?.remediation
        ? { ...item, remediation: adminItem.remediation }
        : item;
      const diagnosis = item.diagnosis
        ? `<div class="benchmark-diagnosis"><b>原因：${escapeHtml(item.diagnosis.label || '')}</b><span>${escapeHtml(item.diagnosis.detail || '')}</span><em>建议：${escapeHtml(item.diagnosis.action || '')}</em>${renderRemediationControls(itemWithAdminState)}</div>`
        : '';
      return `<div class="benchmark-row is-${escapeHtml(item.status || '')}"><span>${labels[item.status] || item.status}</span><b>${title}</b><small>${escapeHtml(fmtDate(item.occurred_at))}</small>${diagnosis}</div>`;
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
    const evidence = (item.corroborating_sources || []).length > 1
      ? ` · ${item.corroborating_sources.length} 源佐证`
      : '';
    return `<div class="benchmark-candidate-row">
      <span>${escapeHtml(item.label || '候选')}</span>
      <div><b>${title}</b><small>${escapeHtml(item.reason || '')}${escapeHtml(evidence)} · ${escapeHtml(item.source || '')} · ${escapeHtml(fmtDate(item.occurred_at))} · 发现用时 ${item.discovery_minutes ?? '—'} 分钟</small></div>
      <button class="ghost sm" data-benchmark-candidate="${index}">加入基准</button>
    </div>`;
  }).join('');
  return `<div class="benchmark-panel">
    <div class="source-value-head"><b>必达事件基准</b><span>近 ${benchmark.window_days || 30} 天 · 准时 ${benchmark.on_time || 0} / 迟到 ${benchmark.late || 0} / 漏报 ${benchmark.missed || 0} / 待闭环 ${benchmark.open_issue_count || 0}</span></div>
    <div class="source-value-empty">独立核验 ${benchmark.origin_breakdown?.independent?.total || 0} 条 · 已抓候选 ${benchmark.origin_breakdown?.candidate?.total || 0} 条 · 普通登记 ${benchmark.origin_breakdown?.manual?.total || 0} 条。候选来自已抓文章，不能单独证明漏报率；当前滚动库也可能已淘汰旧事件。</div>
    ${issueRows}
    <div class="benchmark-admin admin-only">
      <div class="benchmark-candidates">
        <div class="source-value-head"><b>自动发现候选（${candidateItems.length}）</b><span>近 ${candidates?.window_days || 7} 天官方或多源佐证事件 · 人工确认后才计入召回率</span></div>
        ${candidateRows || '<div class="source-value-empty">暂无未登记候选。</div>'}
      </div>
      <div class="benchmark-form">
        <select id="benchmark-origin" aria-label="基准发现方式"><option value="independent">从站外独立发现</option><option value="manual" selected>普通手工登记</option></select>
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

function renderRemediationControls(item) {
  const remediation = item.remediation || { status: 'open' };
  const status = remediation.status || 'open';
  const labels = { open: '待处理', in_progress: '处理中', closed: '已关闭' };
  const outcomes = { fixed: '已修复', accepted: '接受限制', false_positive: '基准误报' };
  const sourceUrl = safeExternalUrl(item.diagnosis?.source?.url);
  const start = status === 'open'
    ? `<button class="ghost sm" data-remediation-action="start" data-benchmark-id="${escapeHtml(item.id || '')}">开始处理</button>`
    : '';
  const reopen = status === 'closed'
    ? `<button class="ghost sm" data-remediation-action="reopen" data-benchmark-id="${escapeHtml(item.id || '')}">重新打开</button>`
    : '';
  const close = status !== 'closed'
    ? `<select data-remediation-outcome><option value="fixed">已修复</option><option value="accepted">接受限制</option><option value="false_positive">基准误报</option></select><button class="ghost sm" data-remediation-close data-benchmark-id="${escapeHtml(item.id || '')}">记录结果</button>`
    : '';
  const recheck = sourceUrl
    ? `<button class="ghost sm" data-remediation-recheck data-benchmark-id="${escapeHtml(item.id || '')}">单源复测</button>`
    : '';
  const discover = item.diagnosis?.code === 'source_not_configured'
    ? `<button class="ghost sm" data-source-discover data-benchmark-id="${escapeHtml(item.id || '')}">发现官方入口</button>`
    : '';
  const outcome = remediation.outcome ? ` · ${outcomes[remediation.outcome] || remediation.outcome}` : '';
  const note = remediation.note
    ? `<small title="处理记录">${escapeHtml(remediation.note)}</small>`
    : '';
  const kindLabels = { rss: 'RSS', atom: 'Atom', sitemap: 'Sitemap', update_page: '更新页' };
  const sourceCandidates = (remediation.source_candidates || []).map(candidate => {
    const candidateUrl = safeExternalUrl(candidate.url);
    if (!candidateUrl) return '';
    const defaultName = (() => {
      try { return new URL(candidateUrl).hostname.replace(/^www\./, ''); } catch { return '官方更新'; }
    })();
    const canActivate = (
      candidate.ready && ['rss', 'atom'].includes(candidate.kind)
    ) || ['sitemap', 'update_page'].includes(candidate.kind);
    const actionLabel = ['sitemap', 'update_page'].includes(candidate.kind) ? '验证并接入' : '接入并试抓';
    const activation = candidate.activated_at
      ? `<div class="source-activation-done">${candidate.source_enabled === false ? '⏸ 已停用：' : '✓ 已接入为 '}${escapeHtml(candidate.activated_name || defaultName)} · 试抓新增 ${Number(candidate.activated_added || 0)} 篇</div>`
      : (canActivate
        ? `<div class="source-activation"><input type="text" maxlength="80" value="${escapeHtml(defaultName)}" aria-label="来源名称"><button class="ghost sm" data-source-activate data-benchmark-id="${escapeHtml(item.id || '')}" data-source-url="${escapeHtml(candidateUrl)}" data-source-kind="${escapeHtml(candidate.kind || '')}" data-action-label="${actionLabel}">${actionLabel}</button></div>`
        : '');
    const readiness = candidate.ready ? '可直接接入' : (canActivate ? '可自动验证适配' : '需适配');
    return `<div class="source-discovery-row"><span>${readiness} · ${escapeHtml(kindLabels[candidate.kind] || candidate.kind || '入口')}</span><a href="${escapeHtml(candidateUrl)}" target="_blank" rel="noopener">${escapeHtml(candidateUrl)}</a><small>${escapeHtml(candidate.evidence || '')}；${escapeHtml(candidate.next_step || '')}</small>${activation}</div>`;
  }).join('');
  const discoveryResults = sourceCandidates
    ? `<div class="source-discovery-results">${sourceCandidates}</div>`
    : (remediation.source_discovery_at ? '<small>本次没有发现通过验证的官方入口。</small>' : '');
  return `<div class="benchmark-remediation admin-only"><span>${labels[status] || status}${escapeHtml(outcome)}</span>${note}${start}${reopen}${recheck}${discover}${close}${discoveryResults}</div>`;
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
        origin: root.querySelector('#benchmark-origin')?.value || 'manual',
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
        origin: 'candidate',
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
  root.querySelectorAll('[data-remediation-action]').forEach(button => button.addEventListener('click', async () => {
    button.disabled = true;
    try {
      await api('PATCH', `/api/ai-news/quality/benchmarks/${encodeURIComponent(button.dataset.benchmarkId)}/remediation`, {
        action: button.dataset.remediationAction,
      });
      await loadSources();
    } catch (error) {
      const msg = root.querySelector('#benchmark-msg');
      if (msg) msg.textContent = error.message || '更新处理状态失败';
      button.disabled = false;
    }
  }));
  root.querySelectorAll('[data-remediation-recheck]').forEach(button => button.addEventListener('click', async () => {
    button.disabled = true;
    button.textContent = '复测中…';
    try {
      const result = await api('POST', `/api/ai-news/quality/benchmarks/${encodeURIComponent(button.dataset.benchmarkId)}/recheck`);
      const msg = root.querySelector('#benchmark-msg');
      if (msg) msg.textContent = `复测完成，本轮新增 ${result.added || 0} 篇；诊断已刷新。`;
      await loadSources();
    } catch (error) {
      const msg = root.querySelector('#benchmark-msg');
      if (msg) msg.textContent = error.message || '单源复测失败';
      button.disabled = false;
      button.textContent = '单源复测';
    }
  }));
  root.querySelectorAll('[data-source-discover]').forEach(button => button.addEventListener('click', async () => {
    button.disabled = true;
    button.textContent = '探测中…';
    try {
      await api('POST', `/api/ai-news/quality/benchmarks/${encodeURIComponent(button.dataset.benchmarkId)}/discover-sources`);
      await loadSources();
    } catch (error) {
      const msg = root.querySelector('#benchmark-msg');
      if (msg) msg.textContent = error.message || '官方入口发现失败';
      button.disabled = false;
      button.textContent = '发现官方入口';
    }
  }));
  root.querySelectorAll('[data-source-activate]').forEach(button => button.addEventListener('click', async () => {
    const name = button.parentElement?.querySelector('input')?.value.trim() || '';
    const msg = root.querySelector('#benchmark-msg');
    if (name.length < 2) {
      if (msg) msg.textContent = '请填写至少 2 个字符的来源名称。';
      return;
    }
    button.disabled = true;
    button.textContent = ['sitemap', 'update_page'].includes(button.dataset.sourceKind) ? '验证中…' : '接入中…';
    try {
      const result = await api('POST', `/api/ai-news/quality/benchmarks/${encodeURIComponent(button.dataset.benchmarkId)}/activate-source`, {
        url: button.dataset.sourceUrl,
        name,
      });
      if (msg) msg.textContent = `来源已接入 fast 层，试抓新增 ${result.added || 0} 篇。`;
      await loadSources();
    } catch (error) {
      if (msg) msg.textContent = error.message || '来源接入失败';
      button.disabled = false;
      button.textContent = button.dataset.actionLabel || '接入并试抓';
    }
  }));
  root.querySelectorAll('[data-remediation-close]').forEach(button => button.addEventListener('click', async () => {
    const note = window.prompt('请简要记录处理结果（至少 3 个字符）');
    if (!note) return;
    const outcome = button.parentElement?.querySelector('[data-remediation-outcome]')?.value || 'fixed';
    button.disabled = true;
    try {
      await api('PATCH', `/api/ai-news/quality/benchmarks/${encodeURIComponent(button.dataset.benchmarkId)}/remediation`, {
        action: 'close', outcome, note,
      });
      await loadSources();
    } catch (error) {
      const msg = root.querySelector('#benchmark-msg');
      if (msg) msg.textContent = error.message || '记录处理结果失败';
      button.disabled = false;
    }
  }));
}

function sourceCard(s) {
  let status, statusClass;
  if (s.health_status === 'disabled') { status = '⏸ 已停用'; statusClass = 'st-disabled'; }
  else if (s.health_status === 'error') { status = '⚠️ 抓取失败'; statusClass = 'st-err'; }
  else if (s.health_status === 'stale') { status = '◷ 调度过期'; statusClass = 'st-stale'; }
  else if (s.health_status === 'healthy') { status = '✓ 正常'; statusClass = 'st-ok'; }
  else { status = '⊝ 尚未抓取'; statusClass = 'st-neutral'; }
  const healthDetail = ['error', 'stale'].includes(s.health_status)
    ? `<div class="src-err ${s.health_status === 'stale' ? 'is-stale' : ''}" title="${escapeHtml(s.last_error || s.health_reason || '')}">${escapeHtml(s.last_error ? (s.last_error.length > 80 ? s.last_error.slice(0, 77) + '…' : s.last_error) : s.health_reason || '')}</div>`
    : '';
  const contentDetail = ['quiet', 'dormant'].includes(s.content_status)
    ? `<div class="src-err is-stale" title="${escapeHtml(s.content_reason || '')}">${escapeHtml(s.content_reason || '')}</div>`
    : '';
  const lastFetch = s.last_fetch ? fmtDate(s.last_fetch) : '—';
  const lastOk = s.last_ok ? fmtDate(s.last_ok) : '—';
  const newestArticle = s.newest_article_at ? fmtDate(s.newest_article_at) : '—';
  const latestEntry = s.latest_entry_at ? fmtDate(s.latest_entry_at) : '—';
  const desc = s.description ? escapeHtml(s.description) : '<span class="text-faint">（无简介）</span>';
  const cadence = { fast: '每小时', standard: '每 4 小时', slow: '每 12 小时' }[s.cadence] || '';
  const host = s.url ? (s.url.replace(/^https?:\/\//, '').split('/')[0] || '') : '';
  const safeUrl = safeExternalUrl(s.url);
  const linkRow = safeUrl
    ? `<a class="src-link" href="${escapeHtml(safeUrl)}" target="_blank" rel="noopener" title="RSS 订阅地址">${escapeHtml(host)} ↗</a>`
    : '<span class="text-faint">（无 URL）</span>';
  const controls = s.custom && safeUrl
    ? `<div class="src-actions admin-only"><button class="ghost sm" data-source-toggle data-source-url="${escapeHtml(safeUrl)}" data-source-enabled="${s.enabled ? 'true' : 'false'}">${s.enabled ? '停用' : '重新启用'}</button><button class="ghost sm danger" data-source-delete data-source-url="${escapeHtml(safeUrl)}" data-source-name="${escapeHtml(s.name || '')}">删除</button></div>`
    : '';
  return `
    <div class="src-card ${s.enabled === false ? 'is-disabled' : ''}">
      <div class="src-card-head">
        ${catBadge(s.category)}
        <div class="src-name">${escapeHtml(s.name)}</div>
        <span class="src-status ${statusClass}">${status}</span>
      </div>
      <div class="src-desc">${desc}</div>
      ${healthDetail}
      ${contentDetail}
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
      <div class="src-stats text-faint"><span title="最近成功抓取">成功 ${lastOk}</span><span class="dot-sep">·</span><span title="源站最新可解析条目">源站最新 ${latestEntry}</span><span class="dot-sep">·</span><span title="当前库中该来源最新文章">入库最新 ${newestArticle}</span></div>
      <div class="src-foot">${linkRow}${controls}</div>
    </div>`;
}

function bindSourceControls(root) {
  root?.querySelectorAll('[data-source-toggle]').forEach(button => button.addEventListener('click', async () => {
    const enable = button.dataset.sourceEnabled !== 'true';
    button.disabled = true;
    button.textContent = enable ? '启用中…' : '停用中…';
    try {
      await api('PATCH', '/api/ai-news/sources/custom', {
        url: button.dataset.sourceUrl,
        enabled: enable,
      });
      await loadSources();
    } catch (error) {
      window.alert(error.message || '更新来源状态失败');
      button.disabled = false;
      button.textContent = enable ? '重新启用' : '停用';
    }
  }));
  root?.querySelectorAll('[data-source-delete]').forEach(button => button.addEventListener('click', async () => {
    const name = button.dataset.sourceName || '这个来源';
    if (!window.confirm(`删除「${name}」的来源配置？已有文章会保留。`)) return;
    button.disabled = true;
    button.textContent = '删除中…';
    try {
      await api('DELETE', `/api/ai-news/sources/custom?url=${encodeURIComponent(button.dataset.sourceUrl || '')}`);
      await loadSources();
    } catch (error) {
      window.alert(error.message || '删除来源失败');
      button.disabled = false;
      button.textContent = '删除';
    }
  }));
}
