import { escapeHtml as esc } from '../util.js';
import { tr } from '../context-panels.js';
import { models, filterModels, readProgress, saveCompletion, clearProgress } from './catalog.js';
import { componentExplanation } from './agent-components.js';
import { agents } from './agents.js';
import { lessons, lessonTrace, lessonOutcome, traceLabels } from './lessons.js';
import { academyUrl, modelCard, modelDetail, modelComparison } from './model-views.js';
import { pretty } from './inspect-panels.js';
import { inspectRequest } from './inspect-request.js';
import { protocolDocs } from './protocol-examples.js';
import './academy.css';
const compared = new Set();
const l = pair => tr(...pair);
function agentDetail(agent) {
  return `<section class="ax-study"><h2>${esc(agent.name)}</h2><p>${esc(l(agent.summary))}</p><p>${tr('依据公开资料整理 · 2026-11-11 · 教学抽象，非真实运行记录或完整内部实现。产品版本与配置会改变行为。', 'Public-documentation summary · 2026-11-11 · A teaching abstraction, not a captured run or complete internals. Behavior varies with version and configuration.')}</p><div class="cx-flow">${agent.components.map((component,i) => `<button data-agent-part="${i}"><small>0${i+1}</small><b>${esc(l(component))}</b><span>${tr('点击查看职责与边界', 'Select to inspect responsibility and boundaries')} →</span></button>`).join('')}</div><div id="ax-agent-part" class="cx-boundary">${tr('选择一个部件。模型、工具、记忆和执行权限属于不同边界。', 'Select a component. Models, tools, memory and execution permissions have different boundaries.')}</div><p><a href="${esc(agent.source)}" target="_blank" rel="noopener noreferrer">${tr('公开来源 ↗', 'Public source ↗')}</a> · <a href="${academyUrl({tab:'lessons',lesson:agent.lesson})}">${tr('进入相关教学轨迹 →', 'Open a related teaching trace →')}</a></p><p>${tr('下方关联案例是通用教学，不是该产品导出的会话。模型读取上下文；应用或服务执行工具、检查权限并选择记忆。', 'The linked case is generic teaching, not an exported session from this product. The model reads context; the app or service runs tools, checks permissions and selects memory.')}</p></section>`;
}
function caseDetail(lesson) {
  const trace = lessonTrace(lesson.id), done = readProgress()[lesson.id] === true;
  return `<section class="ax-study"><h2>${esc(l(lesson.title))}</h2><p>${esc(l(lesson.goal))}</p><p>${tr('前置概念', 'Prerequisites')}: ${esc(lesson.prerequisite)}</p><p>${tr('证据类型：人工教学数据，非真实模型运行；所有输入、工具结果及示例结论均已预写。', 'Evidence type: authored teaching data, not a model run; inputs, tool results and example outcomes are prewritten.')}</p><div class="ax-step">${trace.map((_,i) => `<button data-case-step="${i}" aria-pressed="${i===0}">${i+1}. ${l(traceLabels[i])}</button>`).join('')}</div><div id="ax-case-trace"></div><details><summary>${tr('预写最终答复与证据（非实时生成）', 'Authored final answer and evidence (not live output)')}</summary><p>${esc(l(lessonOutcome(lesson.id)))}</p></details><h3>${tr('动手练习', 'Try it')}</h3><p>${esc(l(lesson.task))}</p><form id="ax-quiz" class="ax-quiz"><h3>${esc(l(lesson.question))}</h3>${lesson.choices.map((choice,i) => `<label><input type="radio" name="answer" value="${i}" required> ${esc(l(choice))}</label>`).join('')}<button type="submit">${tr('检查答案', 'Check answer')}</button><p id="ax-quiz-result" role="status">${done ? tr('✓ 已在本浏览器完成', '✓ Completed in this browser') : ''}</p></form><p><a href="${protocolDocs[lesson.protocol]}" target="_blank" rel="noopener noreferrer">${tr('官方协议参考 ↗', 'Official protocol reference ↗')}</a></p><p>${tr('进度只保存案例完成标记，不保存请求或答案内容；不跨设备同步。', 'Progress stores completion flags only, not requests or answer content. It does not sync across devices.')}</p></section>`;
}
export function loadAcademy() {
  const root = document.querySelector('#academy-root'), params = new URLSearchParams(location.search);
  const tab = params.get('tab') || (params.has('agent') ? 'agents' : 'models');
  const selectedModel = models.find(m => m.id === params.get('model'));
  const selectedAgent = agents.find(a => a.id === params.get('agent'));
  const selectedCase = lessons.find(a => a.id === params.get('lesson'));
  root.innerHTML = `<div class="cx-app"><header class="cx-header"><div><span class="cx-eyebrow">AI FRONTIER / ACADEMY</span><h2>${tr('模型与 Agent 学习库', 'Model & agent academy')}</h2><p>${tr('从最新进展走向模型、上下文和 Agent 的工作机制。', 'Connect AI updates with models, context and agent mechanics.')}</p></div><a href="/context?lang=${document.documentElement.lang === 'en' ? 'en' : 'zh'}">${tr('打开解剖台 →', 'Open inspector →')}</a></header><nav class="cx-tabs">${[['models','模型库','Models'],['agents','Agent 图谱','Agents'],['lessons','学习案例','Lessons']].map(([key,zh,en]) => `<a class="ax-tab ${tab===key?'on':''}" href="${academyUrl({tab:key})}">${tr(zh,en)}</a>`).join('')}</nav><div id="ax-academy-body"></div></div>`;
  const body = root.querySelector('#ax-academy-body');
  if (selectedModel) { body.innerHTML = modelDetail(selectedModel); return; }
  if (selectedAgent) {
    body.innerHTML = agentDetail(selectedAgent);
    body.querySelectorAll('[data-agent-part]').forEach(button => button.onclick = () => {
      const i = Number(button.dataset.agentPart);
      body.querySelector('#ax-agent-part').textContent = l(selectedAgent.components[i]) + ' — ' + componentExplanation(selectedAgent, i);
    }); return;
  }
  if (selectedCase) {
    body.innerHTML = caseDetail(selectedCase); const trace = lessonTrace(selectedCase.id);
    const renderStep = step => {
      const report = inspectRequest(trace[step], selectedCase.protocol);
      body.querySelector('#ax-case-trace').innerHTML = `<div class="ax-metrics"><b>${report.bytes} B</b><span>${report.links.length} ${tr('已出现的工具调用', 'tool calls so far')}</span><a href="/context?${new URLSearchParams({lang:document.documentElement.lang === 'en'?'en':'zh',protocol:selectedCase.protocol,case:selectedCase.id,step:String(step)})}">${tr('在解剖台检查这一轮 →', 'Inspect this turn →')}</a></div>${pretty(trace[step])}`;
      body.querySelectorAll('[data-case-step]').forEach(b => b.setAttribute('aria-pressed',String(Number(b.dataset.caseStep)===step)));
    };
    renderStep(0);body.querySelectorAll('[data-case-step]').forEach(b => b.onclick=()=>renderStep(Number(b.dataset.caseStep)));
    body.querySelector('#ax-quiz').onsubmit=e=>{e.preventDefault();const correct=Number(new FormData(e.target).get('answer'))===selectedCase.answer;const persisted=correct?saveCompletion(selectedCase.id):true;body.querySelector('#ax-quiz-result').textContent=correct?tr('✓ 正确，已完成此案例。','✓ Correct. Case completed.')+(persisted?'':tr(' 存储不可用，仅保留在本次页面。',' Storage unavailable; kept for this session only.')):tr('再检查轨迹：','Review the trace: ')+l(selectedCase.choices[selectedCase.answer]);};return;
  }
  if (tab === 'agents') { body.innerHTML = `<p class="cx-note">${tr('产品、框架与模式分开展示；所有轨迹入口均标注为教学数据。', 'Products, frameworks and patterns are separate; linked traces are labeled teaching data.')}</p><div class="ax-grid">${agents.map(a=>`<article class="ax-card"><span class="ax-tag">${a.type}</span><h3><a href="${academyUrl({agent:a.id,tab:'agents'})}">${esc(a.name)}</a></h3><p>${esc(l(a.summary))}</p><a href="${academyUrl({tab:'lessons',lesson:a.lesson})}">${tr('教学案例 →','Teaching case →')}</a></article>`).join('')}</div>`;return; }
  if (tab === 'lessons') { const progress=readProgress();body.innerHTML=`<p>${lessons.filter(l=>progress[l.id]===true).length} / ${lessons.length} ${tr('案例已完成（本浏览器）','cases completed (this browser)')} <button id="ax-reset-progress">${tr('重置学习进度','Reset progress')}</button></p><div class="ax-grid">${lessons.map(c=>`<article class="ax-card"><span class="ax-tag">${c.protocol}</span><h3><a href="${academyUrl({tab:'lessons',lesson:c.id})}">${esc(l(c.title))}</a></h3><p>${esc(l(c.goal))}</p><span>${progress[c.id]===true?'✓':''}</span><a href="${academyUrl({tab:'lessons',lesson:c.id})}">${tr('开始学习 →','Start lesson →')}</a></article>`).join('')}</div>`;body.querySelector('#ax-reset-progress').onclick=()=>{clearProgress();loadAcademy();};return; }
  body.innerHTML = `<p>${models.length} ${tr('模型资料条目','model references')} · ${new Set(models.map(m=>m.provider)).size} ${tr('提供方','providers')}</p><p class="cx-note">${tr('精选目录，不穷尽全部模型。每条都有来源与核验日期；未知项留空，不做排行榜或可用性保证。','A curated catalog, not every model. Each entry has a source and check date; unknowns remain explicit. No ranking or availability guarantee.')}</p><div class="ax-search"><input id="ax-model-search" aria-label="${tr('搜索模型','Search models')}" placeholder="${tr('模型名称 / 提供方','Model / provider')}" value="${esc(params.get('q')||'')}"><select id="ax-provider" aria-label="Provider"><option value="">${tr('全部提供方','All providers')}</option>${[...new Set(models.map(m=>m.provider))].map(p=>`<option>${esc(p)}</option>`).join('')}</select><select id="ax-task" aria-label="Task"><option value="">${tr('全部类型','All tasks')}</option>${[...new Set(models.map(m=>m.task))].map(p=>`<option>${p}</option>`).join('')}</select><select id="ax-access" aria-label="Deployment"><option value="">${tr('全部部署方式','All deployment types')}</option><option>hosted</option><option>open-weight</option></select></div><p id="ax-model-count" role="status"></p><div id="ax-model-comparison"></div><div id="ax-model-list" class="ax-grid"></div>`;
  const render = () => {
    const found=filterModels(body.querySelector('#ax-model-search').value,body.querySelector('#ax-provider').value,body.querySelector('#ax-task').value,body.querySelector('#ax-access').value);
    body.querySelector('#ax-model-count').textContent=String(found.length)+' '+tr('条结果','results');body.querySelector('#ax-model-list').innerHTML=found.map(m=>modelCard(m,compared)).join('')||tr('没有匹配模型，试试清除筛选。','No matches; try clearing filters.');
    body.querySelector('#ax-model-comparison').innerHTML=modelComparison(compared);
    body.querySelectorAll('[data-model-compare]').forEach(box=>box.onchange=()=>{if(box.checked&&compared.size>=3){box.checked=false;body.querySelector('#ax-model-count').textContent=tr('最多对比3个模型，先取消一项。','Compare up to three models; deselect one first.');return;}box.checked?compared.add(box.dataset.modelCompare):compared.delete(box.dataset.modelCompare);render();});
  };
  for(const id of ['ax-model-search','ax-provider','ax-task','ax-access']) body.querySelector('#'+id).addEventListener(id==='ax-model-search'?'input':'change',render);
  render();
}
