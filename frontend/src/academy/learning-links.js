import { escapeHtml as esc } from '../util.js';
import { tr } from '../context-panels.js';
import { relatedModels } from './catalog.js';
import { agents } from './agents.js';
export function learningLinks(article) {
  const text = [article.title,article.title_zh,article.summary,article.summary_zh].filter(Boolean).join(' ').toLowerCase();
  const language = document.documentElement.lang === 'en' ? 'en' : 'zh';
  const links = relatedModels(text).map(m => ({ label:m.name, params:{model:m.id} }));
  agents.filter(a => a.type==='product' && text.includes(a.name.toLowerCase())).slice(0,2).forEach(a=>links.push({label:a.name,params:{tab:'agents',agent:a.id}}));
  if (!links.length && /\bagents?\b|智能体/.test(text)) links.push({label:tr('Agent 工作机制','Agent mechanics'),params:{tab:'agents'}});
  if (!links.length) return '';
  return `<div class="ax-learning-links"><span>${tr('延伸学习','Learn more')}:</span> ${links.slice(0,3).map(link=>`<a href="/academy?${new URLSearchParams({lang:language,...link.params})}">${esc(link.label)} →</a>`).join(' ')}</div>`;
}
