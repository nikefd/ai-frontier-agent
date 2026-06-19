// Secondary views: today's summary, deep-dive guides, source health.
import { $, $$, escapeHtml, fmtDate, catBadge } from './util.js';
import { api, renderMermaidInside } from './api.js';
import { toggleDive } from './feed.js';

// ── Today's summary ──────────────────────────────────────────────────
export async function loadSummary() {
  const meta = $('#summary-meta'), body = $('#summary-body'), cohort = $('#summary-cohort');
  body.innerHTML = '<div class="muted-card">加载中…</div>';
  try {
    const r = await api('GET', '/api/ai-news/summary/today');
    const s = r.summary;
    cohort.textContent = r.cohort_size
      ? `基于今日 ${r.cohort_size} 篇文章 · 日期 ${r.today || ''}` : `今日候选 0 篇`;
    if (s && s.body) {
      meta.textContent = s.generated_at ? '生成于 ' + fmtDate(s.generated_at) : '';
      body.innerHTML = marked.parse(s.body);
      await renderMermaidInside(body);
    } else {
      meta.textContent = '';
      body.innerHTML = `<div class="muted-card" style="padding:32px 20px">
        ✨ 还没有生成今日速报<br>
        <span class="text-faint" style="font-size:12px">点击右上「重新生成」按钮，会基于最近 24h 候选文章（共 ${r.cohort_size || 0} 篇）调 LLM 生成一份。</span>
      </div>`;
    }
  } catch (e) {
    body.innerHTML = '<div class="muted-card">❌ ' + escapeHtml(e.message) + '</div>';
  }
}

export async function regenSummary() {
  const body = $('#summary-body');
  body.innerHTML = '<div class="muted-card">⏳ 重新生成中（约 20-30s）…</div>';
  try {
    const r = await api('POST', '/api/ai-news/summary/today');
    const s = r.summary || {};
    body.innerHTML = marked.parse(s.body || '');
    $('#summary-meta').textContent = '生成于刚才';
    $('#summary-cohort').textContent = s.cohort_size ? `基于今日 ${s.cohort_size} 篇文章` : '';
    await renderMermaidInside(body);
  } catch (e) {
    body.innerHTML = '<div class="muted-card">❌ ' + escapeHtml(e.message) + '</div>';
  }
}

// ── Deep-dive guides ─────────────────────────────────────────────────
export async function loadGuides() {
  const listEl = $('#guides-list');
  try {
    const dived = await api('GET', '/api/ai-news/articles?limit=100');
    const deepItems = (dived.items || []).filter(a => a.deep_dive_status === 'ok');
    const deepHtml = deepItems.length
      ? `<div class="group" style="margin:4px 0 8px">🧠 已深度解读的文章 (${deepItems.length})</div>`
        + deepItems.map(a => `<div class="article-item" data-dive-aid="${escapeHtml(a.id)}" style="cursor:pointer">
            <div class="article-main">
              <div class="article-title">${escapeHtml(a.title_zh || a.title)}</div>
              <div class="article-meta">${escapeHtml(a.source || '')} · ${fmtDate(a.date)}</div>
            </div>
            <span class="src-link">查看解读 ↗</span>
          </div>`).join('')
      : '';

    const r = await api('GET', '/api/ai-news/guides');
    const guideHtml = r.length
      ? `<div class="group" style="margin:14px 0 8px">📚 主题指南 (${r.length})</div>`
        + r.map(g => `<div class="article-item"><div class="article-main"><div class="article-title">${escapeHtml(g.topic)}</div><div class="article-meta">${escapeHtml(g.depth || '')} · ${fmtDate(g.generated_at)}</div></div></div>`).join('')
      : '';

    $('#cnt-guides').textContent = deepItems.length + (r.length || 0);
    listEl.innerHTML = (deepHtml + guideHtml)
      || '<div class="muted-card">还没有深度解读或指南。去文章流点「深度解读」，或在左上生成一篇指南。</div>';

    $$('#guides-list [data-dive-aid]').forEach(el => {
      el.addEventListener('click', () => {
        const aid = el.dataset.diveAid;
        // jump to the feed tab by clicking its nav button (avoids a circular import)
        $('.side-nav button[data-view="feed"]')?.click();
        setTimeout(() => {
          const card = $(`.article-card[data-aid="${aid}"]`);
          if (card) { card.scrollIntoView({ behavior: 'smooth', block: 'center' }); toggleDive(aid, card); }
        }, 300);
      });
    });
  } catch (e) {
    listEl.innerHTML = '<div class="muted-card">❌ ' + escapeHtml(e.message) + '</div>';
  }
}

export async function genGuide() {
  const topic = $('#guide-topic').value.trim();
  const depth = $('#guide-depth').value;
  if (!topic) return alert('请输入主题');
  const s = $('#guide-status'); s.textContent = '⏳ 生成中…';
  try {
    await api('POST', '/api/ai-news/guides/generate', { topic, depth });
    s.textContent = '✓ 已生成';
    loadGuides();
  } catch (e) { s.textContent = '❌ ' + e.message; }
}

// ── Source health ────────────────────────────────────────────────────
const SRC_CAT_LABELS = {
  vendor: '🏢 厂商官方', blog: '✍️ 专家博客', media: '📰 科技媒体',
  paper: '📄 学术论文', trending: '📈 GitHub Trending', community: '💬 社区', other: '其他',
};
const SRC_ORDER = ['vendor', 'blog', 'media', 'paper', 'trending', 'community'];

export async function loadSources() {
  try {
    const r = await api('GET', '/api/ai-news/sources');
    $('#cnt-sources').textContent = r.length;
    const groups = {};
    for (const s of r) (groups[s.category || 'other'] = groups[s.category || 'other'] || []).push(s);

    const okN = r.filter(s => !s.last_error && s.last_ok).length;
    const errN = r.filter(s => s.last_error).length;
    const neverN = r.filter(s => !s.last_fetch).length;
    const totalArticles = r.reduce((a, s) => a + (s.article_count || 0), 0);
    const healthBar = `
      <div class="src-health">
        <div class="src-health-stats">
          <span class="hs-ok">✓ ${okN} 正常</span>
          ${errN ? `<span class="hs-err">⚠ ${errN} 异常</span>` : ''}
          ${neverN ? `<span class="hs-neutral">⊝ ${neverN} 未抓取</span>` : ''}
          <span class="hs-neutral">· 共 ${r.length} 源 · 累计入库 ${totalArticles} 篇</span>
        </div>
      </div>`;

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
    $('#sources-list').innerHTML = '<div class="muted-card">❌ ' + escapeHtml(e.message) + '</div>';
  }
}

function sourceCard(s) {
  let status, statusClass;
  if (s.last_error) { status = '⚠️ 抓取失败'; statusClass = 'st-err'; }
  else if (s.last_ok) { status = '✓ 正常'; statusClass = 'st-ok'; }
  else { status = '⊝ 尚未抓取'; statusClass = 'st-neutral'; }
  const errDetail = s.last_error
    ? `<div class="src-err" title="${escapeHtml(s.last_error)}">${escapeHtml(s.last_error.length > 80 ? s.last_error.slice(0, 77) + '…' : s.last_error)}</div>`
    : '';
  const lastFetch = s.last_fetch ? fmtDate(s.last_fetch) : '—';
  const desc = s.description || '<span class="text-faint">（无简介）</span>';
  const host = s.url ? (s.url.replace(/^https?:\/\//, '').split('/')[0] || '') : '';
  const linkRow = s.url
    ? `<a class="src-link" href="${escapeHtml(s.url)}" target="_blank" rel="noopener" title="RSS 订阅地址">${escapeHtml(host)} ↗</a>`
    : '<span class="text-faint">（无 URL）</span>';
  return `
    <div class="src-card">
      <div class="src-card-head">
        ${catBadge(s.category)}
        <div class="src-name">${escapeHtml(s.name)}</div>
        <span class="src-status ${statusClass}">${status}</span>
      </div>
      <div class="src-desc">${desc}</div>
      ${errDetail}
      <div class="src-stats">
        <span title="本次入库 / 被过滤"><span class="hs-ok">+${s.last_added ?? 0}</span> <span class="text-faint">/ ${s.last_filtered ?? 0} 过滤</span></span>
        <span class="dot-sep">·</span>
        <span title="累计入库">📚 ${s.article_count || 0} 篇</span>
        <span class="dot-sep">·</span>
        <span title="最近抓取">⏱ ${lastFetch}</span>
      </div>
      <div class="src-foot">${linkRow}</div>
    </div>`;
}
