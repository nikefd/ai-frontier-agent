import { escapeHtml as esc } from '../util.js';
import { tr } from '../context-panels.js';
import { actors, investigationSteps } from './investigation-case.js';
import { routeExperiment, experimentCode, routes } from './route-experiment.js';
import './investigation.css';
const l = pair => tr(...pair);
const checkNames = [['深链不闪首页','No deep-link flash'],['公开内容不等身份','Public content before auth'],['个人内容等待身份','Private content waits'],['根路由保留首页','Root retains landing']];
function experimentView(policy, phase) {
 const result = routeExperiment(policy);
 const state = phase === 'pending' ? result.pending : result.settled;
 return `<section class="iv-experiment"><div><span class="iv-eyebrow">${tr('动手实验 · 确定性模拟','HANDS-ON · DETERMINISTIC SIMULATION')}</span><h3>${tr('把 await 挪一下，会发生什么？','What changes across the await boundary?')}</h3><p>${tr('切换两项修改，再比较身份检查前后。这里计算复现代码的状态，不启动 Agent，也不重跑历史记录。','Toggle two edits and compare states around auth. This computes reproduction states; it does not launch an agent or rerun the recorded task.')}</p></div><div class="iv-controls"><label><input type="checkbox" data-iv-fix="earlyShell" ${policy.earlyShell?'checked':''}>${tr('先按 URL 设置页面外壳','Set route shell before auth')}</label><label><input type="checkbox" data-iv-fix="earlyPublic" ${policy.earlyPublic?'checked':''}>${tr('公开内容在 auth 前加载','Load public content before auth')}</label><label>${tr('观察路由','Observe route')} <select data-iv-route>${routes.map(path=>`<option ${path===policy.path?'selected':''}>${path}</option>`).join('')}</select></label></div><div class="iv-lab-grid"><div><h4>${tr('当前代码顺序','Current code order')}</h4><pre>${esc(experimentCode(policy))}</pre><div class="iv-phase" role="group" aria-label="${tr('身份检查状态','Auth state')}"><button data-iv-phase="pending" aria-pressed="${phase==='pending'}">${tr('① auth 等待中','① Auth pending')}</button><span>→</span><button data-iv-phase="settled" aria-pressed="${phase==='settled'}">${tr('② auth 已完成','② Auth resolved')}</button></div></div><div class="iv-browser" aria-live="polite"><div class="iv-browser-bar">${esc(policy.path)} · ${phase==='pending'?tr('身份未知','Identity pending'):tr('身份已确定','Identity resolved')}</div><div class="iv-browser-screen">${state.landing?`<div class="iv-hero">${tr('每天 10 分钟','10 minutes a day')}<small>${tr('首页仍然可见','Landing page visible')}</small></div>`:''}${state.publicLoads?`<div class="iv-content">${tr('运行拆解内容已加载','Runtime content loaded')}</div>`:''}${state.privateLoads?`<div class="iv-content">${tr('个人实践内容已加载','Private experiments loaded')}</div>`:''}${!state.landing&&!state.publicLoads&&!state.privateLoads?`<p>${tr('路由外壳就绪，内容等待中','Route shell ready; content pending')}</p>`:''}</div><small>${tr('状态示意，不是真实网页截图','State illustration, not a real screenshot')}</small></div></div><div class="iv-checks" aria-live="polite"><b>${tr('四项验收条件的预测 · 不是新测试运行','Predicted acceptance checks · not a new test run')}</b>${result.checks.map((check,i)=>`<span class="${check.pass?'iv-pass':'iv-fail'}">${check.pass?'✓':'×'} ${l(checkNames[i])}</span>`).join('')}</div><button data-iv-reset>${tr('恢复故障顺序','Restore failing order')}</button></section>`;
}
function evidenceRecord(raw, line) {
 if(!raw)return `<p>L${line}: ${tr('记录缺失','Missing record')}</p>`;
 let record;
 try { record=JSON.parse(raw); } catch { return `<pre>${esc(raw)}</pre>`; }
 const item=record.item;
 const content=item?.aggregated_output??item?.text??JSON.stringify(item?.changes??record.usage??record,null,2);
 return `<section><h4>L${line} · ${esc(item?.type||record.type)}</h4>${item?.command?`<code>${esc(item.command)}</code>`:''}${item?.exit_code!==undefined?`<p>exit_code = ${esc(String(item.exit_code))}</p>`:''}<pre>${esc(content)}</pre><details><summary>${tr('查看原始 JSON','Original JSON')}</summary><pre>${esc(JSON.stringify(record,null,2))}</pre></details></section>`;
}
function evidenceView(step, records, error) {
 return `<details class="iv-evidence"><summary>${tr('核对真实采集证据','Verify real capture evidence')} · ${step.lines.map(line=>'L'+line).join(' / ')}</summary><p>${tr('2026-11-11 · Codex CLI 0.166.0 · 独立最小复现 · 已脱敏。以下原文与上面的教学解读分开。','2026-11-11 · Codex CLI 0.166.0 · isolated minimal reproduction · sanitized. Original records are separate from the interpretation above.')}</p>${error?`<p role="alert">${esc(error)}</p><button data-iv-retry>${tr('重新载入证据','Retry evidence')}</button>`:records?step.lines.map(line=>evidenceRecord(records[line-1],line)).join(''):`<p role="status">${tr('正在载入已审查的公开记录…','Loading reviewed public records…')}</p>`}<a href="/runtime?case=codex-route&lang=${document.documentElement.lang==='en'?'en':'zh'}">${tr('进入完整日志检查器 →','Open the full trace inspector →')}</a></details>`;
}
export function mountInvestigation(root) {
 let index=0, answers={}, policy={path:'/runtime',earlyShell:false,earlyPublic:false}, phase='pending', records=null, error='', disposed=false;
 function render() {
  if(disposed || !root.isConnected) return;
  const openEvidence=root.querySelector('.iv-evidence')?.open;
  const openArchitecture=root.querySelector('.iv-architecture')?.open;
  const active=document.activeElement;
  const focusAttribute=active&&root.contains(active)?[...active.attributes].find(a=>a.name.startsWith('data-iv-')):null;
  const step=investigationSteps[index];
  const answer=answers[index];
  root.innerHTML=`<div class="iv-root"><header class="iv-intro"><span class="iv-eyebrow">${tr('一个故障，走通 Agent 的反馈闭环','ONE BUG · THE AGENT FEEDBACK LOOP')}</span><h3>${tr('为什么打开学习页，会先闪回首页？','Why does a learning link flash the homepage?')}</h3><p>${tr('沿真实修复记录探索：谁拿到信息、谁作出动作、什么结果推动下一轮。你可以预测、改顺序、看状态，再核对原文。','Explore a real repair: who receives information, who acts and what feeds the next turn. Predict, change the order, inspect state and verify the records.')}</p></header><nav class="iv-steps" aria-label="${tr('调查步骤','Investigation steps')}">${investigationSteps.map((entry,i)=>`<button data-iv-step="${i}" aria-current="${i===index?'step':'false'}"><small>0${i+1}</small>${esc(l(entry.title))}</button>`).join('')}</nav><div class="iv-flow" role="group" aria-label="${tr('Agent 职责与本步信息流','Agent roles and current information flow')}">${actors.map((actor,i)=>`<button data-iv-actor="${i}" class="${i===step.from?'iv-sender':''} ${i===step.to?'iv-receiver':''}" aria-pressed="${i===step.from||i===step.to}">${esc(l(actor))}<small>${i===step.from?tr('本步发出','Sends this step'):i===step.to?tr('本步接收','Receives this step'):tr('查看职责','Inspect role')}</small></button>`).join('')}</div><div class="iv-packet">${esc(l(actors[step.from]))} <span>→ ${esc(l(step.packet))} →</span> ${esc(l(actors[step.to]))}</div><p id="iv-role" class="iv-role" aria-live="polite">${tr('点击上方部件，查看它负责什么。箭头表示本步关注的信息关系，不是完整网络请求。','Select a component to inspect its responsibility. The arrow highlights this step’s relationship, not a full network request.')}</p><article class="iv-chapter"><span class="iv-eyebrow">0${index+1} / 06</span><h3>${esc(l(step.title))}</h3><div class="iv-io"><section><small>${tr('输入 / 已有证据','INPUT / AVAILABLE EVIDENCE')}</small><p>${esc(l(step.input))}</p></section><span aria-hidden="true">→</span><section><small>${tr('输出 / 状态变化','OUTPUT / STATE CHANGE')}</small><p>${esc(l(step.output))}</p></section></div><p class="iv-explanation">${esc(l(step.why))}</p><fieldset class="iv-prediction"><legend>${esc(l(step.question))}</legend>${step.choices.map((choice,i)=>`<button data-iv-answer="${i}" aria-pressed="${answer===i}">${esc(l(choice))}</button>`).join('')}${answer!==undefined?`<p role="status">${answer===step.correct?tr('判断正确。','Correct.'):tr('再想一下。','Consider this again.')} ${esc(l(step.feedback))}</p>`:''}</fieldset>${evidenceView(step,records,error)}<div class="iv-pagination"><button data-iv-prev ${index===0?'disabled':''}>← ${tr('上一步','Previous')}</button><span>${index+1} / 6</span><button data-iv-next ${index===5?'disabled':''}>${tr('下一步','Next')} →</button></div></article>${experimentView(policy,phase)}<details class="iv-architecture"><summary>${tr('这页自身如何保持 clean architecture？','How is this page structured?')}</summary><p>${tr('案例解释是内容数据；路由实验是无 DOM、无网络的纯函数；界面只负责呈现与交互；真实证据只读取已审查的静态文件。修改讲解不需要改模拟逻辑，修改样式不改变验收条件。','Case interpretation is content data. The route experiment is a pure function without DOM or network access. The view handles presentation and interaction. Evidence comes only from a reviewed static file. Content and styles do not control acceptance logic.')}</p></details></div>`;
  bind();
  root.querySelector('.iv-evidence').open=Boolean(openEvidence);
  root.querySelector('.iv-architecture').open=Boolean(openArchitecture);
  if(focusAttribute)root.querySelector(`[${focusAttribute.name}="${focusAttribute.value}"]`)?.focus({preventScroll:true});
 }
 const roleDescriptions=[
  ['你提供目标和验收边界；模糊目标会让“完成”无法核验。','You supply goals and acceptance boundaries; vague goals make completion hard to verify.'],
  ['运行时负责推进循环、调度工具、收集结果与停止条件。日志只显示其中可观察的部分。','The runtime advances the loop, dispatches tools, collects results and handles stopping. Logs expose only observed portions.'],
  ['模型根据收到的信息输出文字或动作建议；此记录没有完整请求和隐藏思维。','The model produces text or proposed actions from supplied information. Full requests and hidden reasoning are not captured.'],
  ['工具执行读取、命令或修改，返回输出、错误及退出状态。具备工具不等于已经执行。','Tools perform reads, commands or edits and return output, errors and status. Availability is not execution.'],
  ['文件与测试是外部环境：修改影响代码，测试暴露行为；验证范围由断言决定。','Files and tests form the external environment. Edits affect code; assertions determine verification scope.'],
 ];
 function bind() {
  root.querySelectorAll('[data-iv-step]').forEach(button=>button.onclick=()=>{index=Number(button.dataset.ivStep);render();});
  root.querySelectorAll('[data-iv-actor]').forEach(button=>button.onclick=()=>{root.querySelector('#iv-role').textContent=l(roleDescriptions[Number(button.dataset.ivActor)]);});
  root.querySelectorAll('[data-iv-answer]').forEach(button=>button.onclick=()=>{answers[index]=Number(button.dataset.ivAnswer);render();});
  root.querySelector('[data-iv-prev]').onclick=()=>{index=Math.max(0,index-1);render();};
  root.querySelector('[data-iv-next]').onclick=()=>{index=Math.min(5,index+1);render();};
  root.querySelectorAll('[data-iv-fix]').forEach(input=>input.onchange=()=>{policy={...policy,[input.dataset.ivFix]:input.checked};render();});
  root.querySelector('[data-iv-route]').onchange=e=>{policy={...policy,path:e.target.value};render();};
  root.querySelectorAll('[data-iv-phase]').forEach(button=>button.onclick=()=>{phase=button.dataset.ivPhase;render();});
  root.querySelector('[data-iv-reset]').onclick=()=>{policy={path:'/runtime',earlyShell:false,earlyPublic:false};phase='pending';render();};
  root.querySelector('[data-iv-retry]')?.addEventListener('click',loadEvidence);
 }
 async function loadEvidence() {
  error='';render();
  try {
   const response=await fetch('/runtime-cases/codex-route.jsonl');
   if(!response.ok)throw new Error('Evidence HTTP '+response.status);
   const text=await response.text();
   if(disposed)return;
   records=text.trimEnd().split('\n');
  } catch(e) { if(disposed)return;error=tr('证据暂时无法载入：','Evidence unavailable: ')+e.message; }
  render();
 }
 render();loadEvidence();
 return ()=>{disposed=true;};
}
