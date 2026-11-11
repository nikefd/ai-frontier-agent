import { escapeHtml as esc } from '../util.js';
import { tr } from '../context-panels.js';
import { inspectRequest, compareRequests } from './inspect-request.js';
import { pretty } from './inspect-panels.js';
import { lessonNotes } from './lesson-notes.js';
const l=pair=>tr(...pair);
function readable(value) {
 if(typeof value==='string')return value;
 if(value?.type==='function_call')return `${value.name}(${value.arguments})`;
 if(value?.type==='function_call_output')return typeof value.output==='string'?value.output:JSON.stringify(value.output);
 const content=Array.isArray(value)?value:value?.content??value?.parts;
 if(typeof content==='string')return content;
 if(Array.isArray(content))return content.map(part=>part.text??(part.type==='tool_use'?`${part.name}(${JSON.stringify(part.input)})`:part.type==='tool_result'?part.content:part.functionCall?`${part.functionCall.name}(${JSON.stringify(part.functionCall.args)})`:part.functionResponse?JSON.stringify(part.functionResponse.response):JSON.stringify(part))).map(v=>typeof v==='string'?v:JSON.stringify(v)).join('\n');
 return JSON.stringify(value);
}
export function lessonWalkthrough(lesson,trace,step) {
 const report=inspectRequest(trace[step],lesson.protocol);
 const before=step?inspectRequest(trace[step-1],lesson.protocol):null;
 const diff=before?compareRequests(before,report).filter(d=>d.change!=='unchanged'):[];
 const lang=document.documentElement.lang==='en'?'en':'zh';
 return `<div class="ax-turn-intro"><span>${tr('请求快照','Request snapshot')} ${step+1} / ${trace.length}</span><h3>${tr('这一轮为什么存在？','Why does this turn exist?')}</h3><p>${esc(l(lessonNotes[lesson.id][step]))}</p></div><div class="ax-metrics"><b>${report.bytes.toLocaleString()} B</b><span>${report.links.length} ${tr('工具调用','tool calls')}</span><span>${report.results.length} ${tr('已回填结果','supplied results')}</span>${before?`<span>${report.bytes-before.bytes>=0?'+':''}${report.bytes-before.bytes} B · ${diff.length} ${tr('变化块','changed blocks')}</span>`:''}</div><div class="ax-pipeline"><div><small>CONTEXT</small><b>${report.items.filter(i=>i.kind==='system').length} ${tr('指令块','instruction blocks')} + ${report.tools.length} ${tr('工具定义','tool definitions')}</b></div><div><small>CALLS</small><b>${report.links.length} ${tr('历史工具调用','historical tool calls')}</b></div><div><small>RESULTS</small><b>${report.results.filter(r=>!r.error).length} ${tr('结果','results')} / ${report.results.filter(r=>r.error).length} ${tr('错误','errors')}</b></div></div>${report.links.length?`<h4>${tr('调用与结果：逐个核对','Match each call and result')}</h4><div class="ax-table-wrap"><table class="ax-table"><thead><tr><th>ID / ${tr('工具','Tool')}</th><th>${tr('参数','Arguments')}</th><th>${tr('结果','Result')}</th></tr></thead><tbody>${report.links.map(call=>`<tr><th><code>${esc(call.id)}</code><br>${esc(call.name)}</th><td><code>${esc(typeof call.args==='string'?call.args:JSON.stringify(call.args))}</code></td><td>${call.matches.map(result=>`<b class="${result.error?'ax-failed':''}">${result.error?'ERROR':'OK'}</b><p>${esc(readable(result.value))}</p>`).join('')||tr('还未提供','Not supplied yet')}</td></tr>`).join('')}</tbody></table></div>`:''}<h4>${tr('模型实际收到的内容（按请求顺序）','What the model receives (request order)')}</h4><div class="ax-turn-messages">${report.items.filter(i=>i.kind!=='tools'&&i.kind!=='controls').map(item=>`<article class="ax-message"><header><b>${esc(item.role)}</b><code>${esc(item.path)}</code><span>${item.bytes} B</span></header><pre>${esc(readable(item.value))}</pre></article>`).join('')}</div>${diff.length?`<details><summary>${tr('相较上一轮的字段变化','Field changes from the previous turn')}</summary><ul>${diff.map(d=>`<li><b>${d.change}</b> <code>${esc(d.path)}</code></li>`).join('')}</ul></details>`:''}<a class="ax-open-inspector" href="/context?${new URLSearchParams({lang,protocol:lesson.protocol,case:lesson.id,step:String(step)})}">${tr('在解剖台定位、修改和比较这一轮 →','Inspect, edit and compare this turn →')}</a><details><summary>${tr('完整原始请求 JSON','Full original request JSON')}</summary>${pretty(trace[step])}</details>`;
}
