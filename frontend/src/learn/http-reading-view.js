import {escapeHtml as esc} from '../util.js';
import {t} from './trace-view.js';
import {comparisonGuides,requestGuide} from './http-reading-guide.js';
export function readingGuideView(data,index,state){
 const guide=requestGuide(data,index),comparison=comparisonGuides.find(g=>g.id===state.comparison);
 return `<section class="wa-reading"><h3>${t('先选一个问题，沿真实请求对照看','Choose a question and compare the actual requests')}</h3><div class="wa-questions">${comparisonGuides.map(g=>`<button data-guide-id="${g.id}" aria-pressed="${g===comparison}">${t(...g.title)}</button>`).join('')}</div>${comparison?`<div class="wa-comparison"><p>${t(...comparison.note)}</p><div>${comparison.points.map((point,i)=>`<button data-guide-point="${i}" aria-pressed="${data.case_id===(comparison.kind==='repair'?'learn-search-v1':'learn-skill-v1')&&index===point.index&&state.format===point.format}">${t(...point.label)} · #${point.index+1}</button>`).join('<span aria-hidden="true">→</span>')}</div></div>`:`<p class="li-note">${t('每个问题都给出两份对应证据；选好后复制到Inspector，不用猜该看哪一轮。','Each question links two matching pieces of evidence. Select one and copy it to Inspector without guessing which round to inspect.')}</p>`}${guide?`<section class="wa-round"><h4>#${data.exchanges[index].sequence} · ${t(...guide.title)}</h4><dl><dt>${t('请求里已有','Already in the request')}</dt><dd>${t(...guide.before)}</dd><dt>${t('本轮响应','This response')}</dt><dd>${t(...guide.after)}</dd><dt>${t('到哪看证据','Where to inspect')}</dt><dd>${t(...guide.look)}</dd></dl></section>`:''}</section>`;
}
export function bindReadingGuide(root,onSelect){
 root.querySelectorAll('[data-guide-id]').forEach(b=>b.onclick=()=>{const guide=comparisonGuides.find(g=>g.id===b.dataset.guideId);if(guide)onSelect(guide,guide.points[0]);});
 root.querySelectorAll('[data-guide-point]').forEach(b=>b.onclick=()=>{const id=root.querySelector('[data-guide-id][aria-pressed=true]')?.dataset.guideId;const guide=comparisonGuides.find(g=>g.id===id),point=guide?.points[Number(b.dataset.guidePoint)];if(point)onSelect(guide,point);});
}
