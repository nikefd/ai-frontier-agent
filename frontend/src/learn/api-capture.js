import {escapeHtml as esc} from '../util.js';
import {t} from './trace-view.js';
import {requestGuide} from './http-reading-guide.js';
import {readingGuideView,bindReadingGuide} from './http-reading-view.js';
export const INSPECTOR_URL='https://inspector.zhangyangbin.com/';
export function inspectorPayload(exchange,format='request'){
 if(format==='request')return JSON.stringify(exchange.request,null,2);
 return exchange.response_events.map(({capture_merged_deltas,...event})=>`event: ${event.type}\ndata: ${JSON.stringify(event)}`).join('\n\n')+'\n\n';
}
export function apiCaptureView(data,index=0,state={format:'request',comparison:null}){
 const format=state.format||'request';
 const exchange=data.exchanges[index],payload=inspectorPayload(exchange,format),request=format==='request';
 return `<div class="wa-toolbar"><label>${t('实验','Experiment')} <select data-wire-case><option value="repair" ${data.case_id==='learn-search-v1'?'selected':''}>${t('真实修复与Explore · 7请求','Repair + Explore · 7 requests')}</option><option value="skill" ${data.case_id==='learn-skill-v1'?'selected':''}>${t('原生Skill只读检查 · 5请求','Native Skill read-only check · 5 requests')}</option></select></label><span>${esc(data.cli_version)} · DeepSeek Flash</span></div><p class="li-note">${t('选择一次真实采集，复制到现有Inspector解析。此处只选择与导出内容，System、Tools、Messages和响应分析复用Inspector。2026-11-17的新实验独立于旧的九步导读。','Choose a captured exchange and copy it into the existing Inspector. This page selects and exports data; Inspector handles System, Tools, Messages and response analysis. These captures from 2026-11-17 are separate from the older walkthrough.')}</p>${data.skill_source?`<p class="li-note">${t('想看Skill正文怎样注入：选择请求2，复制请求JSON，在Inspector的Messages中查看。该实验只检查，文件未改。','To inspect Skill injection, choose request 2 and copy its request JSON, then inspect Messages in Inspector. This experiment only checks; files stay unchanged.')}</p>`:''}${readingGuideView(data,index,{...state,format})}<div class="wa-layout"><aside class="wa-requests">${data.exchanges.map((r,i)=>`<button data-wire-request="${i}" aria-pressed="${i===index}"><b>#${r.sequence} · ${r.scope==='child'?'Explore':t('主任务','Main')}</b>${requestGuide(data,i)?`<span class="wa-request-title">${t(...requestGuide(data,i).title)}</span>`:''}<small>${r.request.messages?.length||0} messages · ${r.request.tools?.length||0} tools</small><small>HTTP ${r.status} · ${r.duration_ms} ms</small></button>`).join('')}</aside><article class="wa-detail"><nav><button data-wire-format="request" aria-pressed="${request}">${t('请求JSON → Inspector ①','Request JSON → Inspector ①')}</button><button data-wire-format="response" aria-pressed="${!request}">${t('响应SSE → Inspector ②','Response SSE → Inspector ②')}</button></nav><div class="wa-body"><h3>${t('在Inspector中查看','Inspect in Inspector')}</h3><ol class="wa-instructions"><li>${t('点击下方按钮，复制当前内容并打开Inspector。','Click below to copy the current payload and open Inspector.')}</li><li>${request?t('在“① 解析请求 Body”的左侧输入框粘贴。','Paste into the left input of “① 解析请求 Body”.'):t('切换到“② 解析 SSE 输出”，在左侧输入框粘贴。','Switch to “② 解析 SSE 输出” and paste into the left input.')}</li><li>${t('点“解析 ▸”，使用原来的分区、参数树与消息分析。','Click “解析 ▸” to use the existing sections, parameter trees and message analysis.')}</li></ol><div class="wa-actions"><button data-wire-copy-open>${t('复制内容并打开Inspector ↗','Copy payload and open Inspector ↗')}</button><button data-wire-copy>${t('仅复制','Copy only')}</button><button data-wire-download>${request?t('下载JSON','Download JSON'):t('下载SSE','Download SSE')}</button><a href="${INSPECTOR_URL}" target="_blank" rel="noopener noreferrer">${t('打开Inspector ↗','Open Inspector ↗')}</a></div><p data-wire-status role="status" aria-live="polite"></p><details class="wa-export"><summary>${t('查看导出内容 / 手动复制','Preview export / copy manually')} · ${new TextEncoder().encode(payload).length.toLocaleString()} B</summary><label>${request?t('请求正文JSON','Request body JSON'):t('审查后合并的SSE','Reviewed, coalesced SSE')}<textarea data-wire-payload readonly rows="12" spellcheck="false">${esc(payload)}</textarea></label><button data-wire-select>${t('选中全部内容','Select all content')}</button></details></div></article></div><p class="li-note">${t('只复制当前选中的请求正文或SSE，不含采集包装信息。认证头未记录；公开内容已脱敏。SSE已去除思考块并合并增量，不保留原始分片边界。内容不放进外站URL，打开页面不会自动上传采集。','Only the selected request body or SSE is copied, without the capture wrapper. Auth headers were never recorded; public content is redacted. Thinking blocks are removed and SSE deltas coalesced; original fragment boundaries are not retained. Payloads are not placed in external URLs or uploaded by opening the page.')}</p>`;
}
export function mountApiCapture(root){
 let disposed=false,generation=0,data=null,index=0,format='request',comparison=null,copyGeneration=0;
 async function load(kind,target={index:0,format:'request',comparison:null}){const current=++generation;copyGeneration++;root.textContent=t('正在载入真实API采集…','Loading actual API capture…');try{const response=await fetch(`/learn/examples/http-${kind}.json`);if(!response.ok)throw new Error('HTTP '+response.status);const result=await response.json();if(disposed||current!==generation)return;data=result;index=target.index;format=target.format;comparison=target.comparison;render();if(comparison)root.querySelector(`[data-guide-id="${comparison}"]`)?.focus({preventScroll:true});}catch(error){if(!disposed&&current===generation){root.textContent=t('采集载入失败：','Capture load failed: ')+error.message;const retry=document.createElement('button');retry.textContent=t('重试','Retry');retry.onclick=()=>load(kind,target);root.append(retry);}}}
 async function copy(open){
  const current=++copyGeneration,payload=inspectorPayload(data.exchanges[index],format);
  try{
   await navigator.clipboard.writeText(payload);
   if(disposed||current!==copyGeneration)return;
   if(open)window.open(INSPECTOR_URL,'_blank','noopener,noreferrer');
   root.querySelector('[data-wire-status]').textContent=t('已复制。在Inspector粘贴后点“解析 ▸”。如未打开，可使用旁边的链接。','Copied. Paste in Inspector and click “解析 ▸”. If no tab opened, use the adjacent link.');
  }catch{
   if(disposed||current!==copyGeneration)return;
   root.querySelector('.wa-export').open=true;root.querySelector('[data-wire-payload]').select();
   root.querySelector('[data-wire-status]').textContent=t('浏览器未允许自动复制。内容已选中，请按⌘C / Ctrl+C，再打开Inspector粘贴。','Automatic copy was unavailable. Text is selected: press ⌘C / Ctrl+C, then open Inspector and paste.');
  }
 }
 function render(){
  copyGeneration++;root.innerHTML=apiCaptureView(data,index,{format,comparison});
  bindReadingGuide(root,(guide,point)=>{
   const target={index:point.index,format:point.format,comparison:guide.id};
   if(data.case_id===(guide.kind==='repair'?'learn-search-v1':'learn-skill-v1')){index=target.index;format=target.format;comparison=guide.id;render();root.querySelector(`[data-guide-id="${guide.id}"]`)?.focus({preventScroll:true});}
   else load(guide.kind,target);
  });
  root.querySelector('[data-wire-download]').onclick=()=>{
   const blob=new Blob([inspectorPayload(data.exchanges[index],format)],{type:format==='request'?'application/json;charset=utf-8':'text/event-stream;charset=utf-8'});
   const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=`${data.case_id}-request-${index+1}.${format==='request'?'json':'sse'}`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
   root.querySelector('[data-wire-status]').textContent=t('已生成下载文件。在Inspector点“载入文件”选择它即可。','Download generated. Use “载入文件” in Inspector to select it.');
  };
  root.querySelector('[data-wire-case]').onchange=e=>load(e.target.value);
  root.querySelectorAll('[data-wire-request]').forEach(b=>b.onclick=()=>{index=Number(b.dataset.wireRequest);render();root.querySelector(`[data-wire-request="${index}"]`)?.focus({preventScroll:true});});
  root.querySelectorAll('[data-wire-format]').forEach(b=>b.onclick=()=>{format=b.dataset.wireFormat;render();root.querySelector(`[data-wire-format="${format}"]`)?.focus({preventScroll:true});});
  root.querySelector('[data-wire-copy-open]').onclick=()=>copy(true);root.querySelector('[data-wire-copy]').onclick=()=>copy(false);
  root.querySelector('[data-wire-select]').onclick=()=>root.querySelector('[data-wire-payload]').select();
 }
 load('repair');return ()=>{disposed=true;generation++;copyGeneration++;data=null;root.innerHTML='';};
}
