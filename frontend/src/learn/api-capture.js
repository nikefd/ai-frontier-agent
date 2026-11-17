import {escapeHtml as esc} from '../util.js';
import {t} from './trace-view.js';
const pre=value=>`<pre>${esc(typeof value==='string'?value:JSON.stringify(value,null,2))}</pre>`;
export function assembleResponse(events){
 const blocks=new Map();let usage={},stopReason='',model='';
 for(const e of events){
  if(e.type==='message_start'){model=e.message?.model||'';usage={...usage,...e.message?.usage};}
  if(e.type==='content_block_start')blocks.set(e.index,{...e.content_block});
  if(e.type==='content_block_delta'){
   const b=blocks.get(e.index);if(!b)continue;
   if(e.delta?.type==='text_delta')b.text=(b.text||'')+e.delta.text;
   if(e.delta?.type==='input_json_delta')b.partial=(b.partial||'')+e.delta.partial_json;
  }
  if(e.type==='message_delta'){usage={...usage,...e.usage};stopReason=e.delta?.stop_reason||stopReason;}
 }
 return {model,stopReason,usage,blocks:[...blocks.values()].map(b=>{if(!b.partial)return b;const {partial,...rest}=b;try{return {...rest,input:JSON.parse(partial)};}catch{return {...rest,unparsed_input:partial};}})};
}
function requestView(body,tab){
 if(tab==='system')return `<h3>System · ${body.system?.length||0} ${t('块','blocks')}</h3>${(body.system||[]).map((b,i)=>`<details ${i===2?'open':''}><summary>#${i} · ${esc(b.type)} · ${b.text?.length||0} ${t('字符','characters')}</summary>${pre(b.text||b)}${b.cache_control?pre({cache_control:b.cache_control}):''}</details>`).join('')}`;
 if(tab==='tools')return `<h3>Tools · ${body.tools?.length||0}</h3>${(body.tools||[]).map(tool=>`<details ${tool.name==='Skill'?'open':''}><summary>${esc(tool.name)} · ${Object.keys(tool.input_schema?.properties||{}).length} ${t('参数','parameters')}</summary><p>${esc(tool.description||'')}</p><h4>input_schema</h4>${pre(tool.input_schema||tool)}</details>`).join('')}`;
 if(tab==='messages')return `<h3>Messages · ${body.messages?.length||0}</h3>${(body.messages||[]).map((m,i)=>`<details ${JSON.stringify(m.content).includes('A failed test is an observed finding')?'open':''}><summary>#${i+1} · ${esc(m.role)}${JSON.stringify(m.content).includes('A failed test is an observed finding')?' · '+t('Skill正文注入','Skill body injected'):''} · ${Array.isArray(m.content)?m.content.map(b=>esc(b.type)).join(' / '):'text'}</summary>${typeof m.content==='string'?pre(m.content):(m.content||[]).map(b=>`<h4>${esc(b.type)}${b.name?' · '+esc(b.name):''}</h4>${pre(b.type==='text'?b.text:b.type==='tool_result'?b.content:b)}`).join('')}</details>`).join('')}`;
 return pre(body);
}
export function apiCaptureView(data,index=0,tab='system'){
 const exchange=data.exchanges[index],body=exchange.request,response=assembleResponse(exchange.response_events);
 const tabs=[['system','System'],['tools','Tools / Schema'],['messages','Messages'],['response',t('响应 / SSE','Response / SSE')],['raw',t('请求JSON','Request JSON')]];
 return `<div class="wa-toolbar"><label>${t('实验','Experiment')} <select data-wire-case><option value="repair" ${data.case_id==='learn-search-v1'?'selected':''}>${t('真实修复与Explore · 7请求','Repair + Explore · 7 requests')}</option><option value="skill" ${data.case_id==='learn-skill-v1'?'selected':''}>${t('原生Skill只读检查 · 5请求','Native Skill read-only check · 5 requests')}</option></select></label><span>${esc(data.cli_version)} · DeepSeek Flash</span></div><p class="li-note">${t('2026-11-17新采集，独立于旧的九步导读。下方是某一次真实发送的请求正文与响应事件，不是CLI日志拼出的上下文。认证头未记录；账户元数据、私有路径、思考块及签名已去除。','New capture on 2026-11-17, separate from the older nine-step walkthrough. Each entry is an actual transmitted request body and response events, not context inferred from CLI logs. No auth headers recorded; account metadata, private paths, thinking blocks and signatures removed.')}</p>${data.skill_source?`<details><summary>${t('本实验自己的SKILL.md原文','This exercise’s own SKILL.md')}</summary>${pre(data.skill_source)}<p>${t('文件保持不变，故障测试仍为2通过/5失败；此实验检查而不修复。可在请求1的响应看到Skill调用，再在后续Messages找到注入的正文。','Files remain unchanged, with 2 passes / 5 failures; this experiment inspects without repairing. Request 1’s response contains the Skill call; subsequent Messages contain the injected instructions.')}</p></details>`:''}<div class="wa-layout"><aside class="wa-requests">${data.exchanges.map((r,i)=>`<button data-wire-request="${i}" aria-pressed="${i===index}"><b>#${r.sequence} · ${r.scope==='child'?'Explore':t('主任务','Main')}</b><small>${r.request.messages?.length||0} messages · ${r.request.tools?.length||0} tools</small><small>HTTP ${r.status} · ${r.duration_ms} ms</small></button>`).join('')}</aside><article class="wa-detail"><nav>${tabs.map(([key,title])=>`<button data-wire-tab="${key}" aria-pressed="${tab===key}">${title}</button>`).join('')}</nav><div class="wa-body">${tab==='response'?`<h3>${t('由真实SSE片段重组','Reassembled from captured SSE fragments')}</h3>${pre({model:response.model,stop_reason:response.stopReason,usage:response.usage})}${response.blocks.map(b=>`<h4>${esc(b.type)}${b.name?' · '+esc(b.name):''}</h4>${pre(b.type==='text'?b.text:b)}`).join('')}<details><summary>${t('脱敏合并后的SSE事件JSON','Redacted, coalesced SSE event JSON')} · ${exchange.response_events.length}</summary>${pre(exchange.response_events)}</details>`:requestView(body,tab)}</div></article></div><p class="li-note">${t('请求序号按采集器收到的顺序排列，不等于模型Turn编号。响应Token来自提供方usage字段，未经账单核验；思考内容过滤后不在正文中。文本及参数片段先合并再脱敏，不保留原始分片边界。','Request numbers follow capture arrival order, not model turn numbers. Tokens come from provider usage, not verified billing; filtered thinking content is absent from the body. Text and parameter deltas are coalesced before redaction; original fragment boundaries are not retained.')}</p>`;
}
export function mountApiCapture(root){
 let disposed=false,generation=0,data=null,index=0,tab='system';
 async function load(kind){const current=++generation;root.textContent=t('正在载入真实API采集…','Loading actual API capture…');try{const response=await fetch(`/learn/examples/http-${kind}.json`);if(!response.ok)throw new Error('HTTP '+response.status);const result=await response.json();if(disposed||current!==generation)return;data=result;index=0;tab='system';render();}catch(error){if(!disposed&&current===generation)root.textContent=t('采集载入失败：','Capture load failed: ')+error.message;}}
 function render(){
  root.innerHTML=apiCaptureView(data,index,tab);
  root.querySelector('[data-wire-case]').onchange=e=>load(e.target.value);
  root.querySelectorAll('[data-wire-request]').forEach(b=>b.onclick=()=>{index=Number(b.dataset.wireRequest);render();root.querySelector(`[data-wire-request="${index}"]`)?.focus({preventScroll:true});});
  root.querySelectorAll('[data-wire-tab]').forEach(b=>b.onclick=()=>{tab=b.dataset.wireTab;render();root.querySelector(`[data-wire-tab="${tab}"]`)?.focus({preventScroll:true});});
 }
 load('repair');return ()=>{disposed=true;generation++;data=null;root.innerHTML='';};
}
