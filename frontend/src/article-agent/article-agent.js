import { isAuthed, openAuthModal } from '../auth.js';
import { language } from '../i18n.js';
import { escapeHtml as esc } from '../util.js';
import { newRun, receiveEvent, readEvents } from './run-state.js';
import { renderRun, t } from './run-view.js';
import './article-agent.css';
export function mountArticleAgent(root) {
 let state=newRun(),controller=null,generation=0;
 root.innerHTML=`<details class="ar-panel"><summary><span>${t('让 Agent 帮我找文章','Find articles with an agent')}</span><small>${t('真实 DeepSeek · 查看执行过程','Live DeepSeek · inspect execution')}</small></summary><div class="ar-body"><p>${t('输入一个研究问题，看它实际搜索、读取和整理本站文章。只读操作；使用现有 AI 额度，最多 5 次模型调用。','Ask a research question and watch real searches and reads in this site’s library. Read-only; uses your AI quota, up to 5 model calls.')}</p><form id="ar-form"><label for="ar-question">${t('你想了解什么？','What would you like to research?')}</label><textarea id="ar-question" rows="2" maxlength="2000" required>${esc(t('帮我找最近关于 Agent 记忆机制的文章，推荐三篇值得读的，解释区别。','Find recent articles about agent memory. Recommend up to three and explain their differences.'))}</textarea><div class="ar-actions"><button type="submit" class="primary" id="ar-start">${t('开始真实运行','Start live run')}</button><button type="button" id="ar-stop" disabled>${t('停止','Stop')}</button><button type="button" id="ar-clear">${t('清空','Clear')}</button><span id="ar-error" role="alert"></span></div></form><div id="ar-run"></div><p class="ar-footnote">${t('这是基础工具循环，不含多 Agent、独立核验或全网检索。读取的是本站保存的摘要与已有解读；原文需打开来源。运行记录仅留在当前页面，刷新会清除。','This is a basic tool loop without multiple agents, independent verification or web-wide search. Reads use stored summaries and existing analyses; open the source for original text. Run records stay on this page and clear on refresh.')}</p></div></details>`;
 const output=root.querySelector('#ar-run'),form=root.querySelector('form'),start=root.querySelector('#ar-start'),stop=root.querySelector('#ar-stop'),error=root.querySelector('#ar-error');
 function render(){const focused=output.contains(document.activeElement)?document.activeElement.dataset.arEvent:undefined;const opened=[...output.querySelectorAll('details')].map(el=>el.open);output.innerHTML=renderRun(state);output.querySelectorAll('details').forEach((el,i)=>{if(opened[i]!==undefined)el.open=opened[i];});output.querySelectorAll('[data-ar-event]').forEach(button=>button.onclick=()=>{state={...state,selected:Number(button.dataset.arEvent)};render();});if(focused!==undefined)output.querySelector(`[data-ar-event="${focused}"]`)?.focus({preventScroll:true});}
 function finish(){controller=null;start.disabled=false;stop.disabled=true;}
 form.onsubmit=async event=>{
  event.preventDefault();if(controller)return;
  if(!isAuthed()){openAuthModal(t('请先登录后再使用 Agent','Please sign in to use the agent'));return;}
  const message=root.querySelector('#ar-question').value.trim();if(!message)return;
  const current=++generation;controller=new AbortController();start.disabled=true;stop.disabled=false;error.textContent='';state={...newRun(),status:'running'};render();
  try{
   const response=await fetch('/api/agent/research',{method:'POST',headers:{'content-type':'application/json','accept-language':language},body:JSON.stringify({message}),signal:controller.signal});
   if(!response.ok){const body=await response.json().catch(()=>({}));if(response.status===401)openAuthModal();throw new Error(body.detail||'HTTP '+response.status);}
   await readEvents(response,event=>{if(current!==generation)return;state=receiveEvent(state,event);if(event.type==='error')error.textContent=event.message;render();});
   if(current===generation&&state.status==='running')throw new Error(t('连接已结束，但没有收到完成结果。','The stream ended without a completion result.'));
  }catch(e){if(current!==generation)return;if(e.name==='AbortError')state={...state,status:'stopped'};else{state={...state,status:'failed'};error.textContent=e.message;}render();}
  finally{if(current===generation)finish();}
 };
 stop.onclick=()=>controller?.abort();
 root.querySelector('#ar-clear').onclick=()=>{generation++;controller?.abort();finish();state=newRun();error.textContent='';render();};
 window.addEventListener('aif:auth-changed',()=>{generation++;controller?.abort();finish();state=newRun();error.textContent='';render();});
 render();
}
