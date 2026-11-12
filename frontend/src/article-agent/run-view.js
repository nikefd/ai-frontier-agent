import { escapeHtml as esc, safeExternalUrl } from '../util.js';
import { isEnglish } from '../i18n.js';
import { renderMarkdown } from '../markdown.js';
import { foundArticles } from './run-state.js';
export const t=(zh,en)=>isEnglish()?en:zh;
const names={model_request:['发送上下文','Send context'],model_response:['模型返回','Model response'],tool_call:['执行工具','Execute tool'],tool_result:['结果回填','Feed back result'],final:['完成回答','Final answer'],error:['运行出错','Run error'],cancelled:['已停止','Stopped']};
const name=e=>t(...(names[e.type]||[e.type,e.type]));
const pretty=value=>`<pre>${esc(typeof value==='string'?value:JSON.stringify(value,null,2))}</pre>`;
function inspection(event) {
 if(!event)return `<p>${t('运行后，点击上下文、模型或工具，检查真实数据。','Run a task, then select context, model or tools to inspect real data.')}</p>`;
 let content='';
 if(event.type==='model_request'){
  content=`<p>${t('以下正文就是这一轮发送的请求，不包含认证头。工具结果只在完成后进入后续请求。','This is the request body sent this turn, excluding auth headers. Tool results enter subsequent requests after execution.')}</p>${event.payload.messages.map((message,i)=>`<details class="ar-message" ${i===event.payload.messages.length-1?'open':''}><summary>${i+1}. ${esc(message.role)}${message.tool_call_id?' · '+esc(message.tool_call_id):''} · ${new TextEncoder().encode(JSON.stringify(message)).length.toLocaleString()} B</summary>${pretty(message.content||message)}${message.tool_calls?pretty(message.tool_calls):''}</details>`).join('')}<details><summary>${t('本轮工具定义','Tool definitions')}</summary>${pretty(event.payload.tools||[])}</details><details><summary>${t('完整请求正文','Full request body')}</summary>${pretty(event.payload)}</details>`;
 }else if(event.type==='model_response'){
  content=`<p>${event.elapsed_ms} ms · ${t('API 报告的 usage','API-reported usage')}</p>${pretty(event.usage)}${event.message.content?pretty(event.message.content):''}${event.message.tool_calls?pretty(event.message.tool_calls):''}`;
 }else if(event.type==='tool_call')content=`<p>${t('模型提出动作，运行时随后执行。','The model proposed this action; the runtime executes it next.')}</p>${pretty(event.arguments)}`;
 else if(event.type==='tool_result')content=`<p>${t('这是实际回填的文本；完整结果与回填可能因长度限制而不同。','This is the actual feedback text. Full output may differ because of the length limit.')}${event.truncated?' '+t('本次已截断。','Truncated in this run.'):''}</p>${pretty(event.content)}<details><summary>${t('完整工具输出','Full tool output')}</summary>${pretty(event.result)}</details>`;
 else content=pretty(event.content||event.message||name(event));
 return `<h4>${esc(name(event))}${event.turn?' · Turn '+event.turn:''}</h4>${event.name?`<p><code>${esc(event.name)}</code> · ${esc(event.call_id||'')}</p>`:''}${content}`;
}
export function renderRun(state) {
 const events=state.events,latest=type=>events.findLastIndex(e=>type.includes(e.type));
 const selected=events[state.selected];
 const last=events.at(-1);
 const activeKind=last?.type==='model_request'?'model':['tool_call','tool_result'].includes(last?.type)?'tools':last?.type==='model_response'?'context':'';
 const columns=[{title:t('本轮上下文','Context'),index:latest(['model_request']),kind:'context'}, {title:t('DeepSeek / 模型','DeepSeek / model'),index:latest(['model_response','model_request']),kind:'model'},{title:t('文章工具 / 环境','Article tools / environment'),index:latest(['tool_call','tool_result']),kind:'tools'}];
 const status={idle:t('等待任务','Ready'),running:t('真实运行中','Running live'),completed:t('已完成','Completed'),failed:t('未完成 · 出错','Incomplete · error'),stopped:t('已停止后续调用','Further calls stopped')};
 const answer=events.findLast(e=>e.type==='final');
 const articles=foundArticles(events);
 const usage=events.filter(e=>e.type==='model_response');
 const completeUsage=usage.length&&usage.every(e=>typeof e.usage?.prompt_tokens==='number'&&typeof e.usage?.completion_tokens==='number');
 return `<div class="ar-status" role="status"><span class="ar-dot ${state.status}"></span>${esc(status[state.status])}<span>${usage.length} ${t('次模型响应','model responses')}${completeUsage?' · '+usage.reduce((sum,e)=>sum+(e.usage?.prompt_tokens||0),0).toLocaleString()+' input / '+usage.reduce((sum,e)=>sum+(e.usage?.completion_tokens||0),0).toLocaleString()+' output tokens':''}</span></div><div class="ar-workspace"><section class="ar-results"><h3>${t('Agent 的回答','Agent answer')}</h3>${answer?renderMarkdown(answer.content):`<p class="ar-muted">${t('搜索与阅读后，回答会出现在这里。基础工具循环最多 5 次模型调用，不保证每次都选择工具。','The answer appears here after research. This basic tool loop allows at most 5 model calls; tool use is not guaranteed.')}</p>`}<h4>${t('本次实际找到的文章','Articles actually found')} · ${articles.length}</h4><div class="ar-articles">${articles.map(article=>{const url=safeExternalUrl(article.url);return `<article><small>${esc(article.publication||article.source||'')} ${article.read?'· '+t('已读取详情','Details read'):''}</small><b>${esc(article.title_zh||article.title||article.id)}</b>${article.date?`<small>${esc(article.date)}</small>`:''}<p>${esc((article.summary||'').slice(0,240))}</p>${url?`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${t('阅读原文 ↗','Read original ↗')}</a>`:''}<a href="/feed?${new URLSearchParams({q:article.title_zh||article.title||article.id,lang:isEnglish()?'en':'zh'})}">${t('在文章流中查看 / 收藏','View / save in the feed')}</a></article>`;}).join('')||`<p class="ar-muted">${t('还没有文章结果。没有结果也会如实保留。','No articles returned yet. Empty results remain visible.')}</p>`}</div></section><section class="ar-process"><h3>${t('正在怎样完成任务','How the task runs')}</h3><div class="ar-flow">${columns.map(column=>{const e=events[column.index];return `<button data-ar-event="${column.index}" ${column.index<0?'disabled':''} aria-pressed="${state.selected===column.index}" class="ar-${column.kind} ${state.status==='running'&&activeKind===column.kind?'ar-active':''}"><b>${column.title}</b><span>${e?esc(name(e)):t('等待输入','Waiting')}${e?.turn?' · '+e.turn:''}</span>${e?.type==='model_request'?`<small>${e.payload.messages.length} ${t('条消息','messages')}</small>`:e?.name?`<small>${esc(e.name)}</small>`:''}</button>`;}).join('')}</div><p class="ar-flow-caption">${t('上下文 → 模型 → 工具 → 结果加入下一轮上下文','Context → model → tools → results enter the next context')}</p><div class="ar-timeline" aria-label="${t('实际执行时间线','Actual execution timeline')}">${events.map((e,i)=>`<button data-ar-event="${i}" aria-pressed="${i===state.selected}"><small>${i+1}${e.turn?' / T'+e.turn:''}</small>${esc(name(e))}${e.name?' · '+esc(e.name):''}</button>`).join('')}</div><div class="ar-inspector">${inspection(selected)}</div></section></div>`;
}
