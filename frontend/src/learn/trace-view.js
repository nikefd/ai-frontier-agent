import {escapeHtml as esc} from '../util.js';
import {isEnglish} from '../i18n.js';
import {renderMarkdown} from '../markdown.js';
import {traceTree} from './trace-model.js';
export const t=(zh,en)=>isEnglish()?en:zh;
const labels={Read:['读取文件','Read file'],Bash:['运行命令','Run command'],Edit:['修改文件','Edit file'],Write:['写入文件','Write file'],Agent:['子任务','Subagent'],Task:['子任务','Subagent']};
export function nodeTitle(node){
 if(node.kind==='call')return t(...(Object.hasOwn(labels,node.title)?labels[node.title]:[node.title,node.title]));
 if(node.kind==='config')return t('初始化配置','Initialization settings');
 if(node.kind==='final')return t('本轮结束','Run result');
 if(node.kind==='message')return node.title==='assistant'?t('助手消息','Assistant message'):t('用户消息','User message');
 return t('未关联结果','Unmatched result');
}
const pretty=value=>`<pre>${esc((typeof value==='string'?value:JSON.stringify(value??'',null,2)).slice(0,16000))}</pre>`;
export function outline(report,selected,limit){
 let shown=0;
 function branch(node,depth){if(shown++>=limit)return '';const hint=node.input?.file_path||node.input?.command||node.input?.description||node.text||'';
 const button=`<button data-lens-node="${node.order}" aria-pressed="${selected===node.order}"><span>${esc(nodeTitle(node))}</span><small>${esc((typeof hint==='string'?hint:JSON.stringify(hint)).slice(0,90))}</small><em class="ln-${node.status}">${esc(node.status)}</em></button>`;
 if(node.children.length&&depth<7)return `<details open class="ln-branch"><summary>${t('子任务轨迹','Child trajectory')} · ${node.children.length}</summary>${button}<div>${node.children.map(child=>branch(child,depth+1)).join('')}</div></details>`;
 return button+(node.children.length?`<p>${t('更深层级请在原始记录中查看。','Inspect deeper levels in the raw records.')}</p>`:'');
 }
 return traceTree(report.nodes).map(node=>branch(node,0)).join('');
}
export function nodeDetail(node,parsed){
 if(!node)return `<p class="ln-empty">${t('载入记录后，选择一项动作，查看它的输入与实际结果。','Load a trace and select an action to inspect its input and actual result.')}</p>`;
 return `<h3>${esc(nodeTitle(node))}</h3><p class="ln-meta">${node.lines.map(line=>(parsed.kind==='array'?'#':'L')+line).join(', ')} · ${t('运行段','Run segment')} ${node.segment+1} · ${esc(node.status)}</p>${node.kind==='call'?`<h4>${t('输入','Input')}</h4>${pretty(node.input)}<h4>${t('执行结果','Execution result')}</h4>${node.output!==undefined?pretty(node.output):`<p>${t('当前回放位置尚无对应结果。','No matching result at this replay position.')}</p>`}`:node.kind==='final'?renderMarkdown(node.text):pretty(node.text)}<details><summary>${t('原始记录与关联信息','Raw records and association information')}</summary><p>${esc(node.id||'')}${node.parentId?' · parent: '+esc(node.parentId):''}</p>${node.lines.length>10?`<p>${t('此处显示最近10条关联记录。','Showing the latest 10 associated records.')}</p>`:''}${node.lines.slice(-10).map(line=>pretty(parsed.rows.find(row=>row.line===line)?.data)).join('')}</details><p class="ln-meta">${t('记录可见信息不等于完整模型请求或隐藏内部过程。输出显示最多16,000字符，原始导入仍保留在本页内存。','Recorded observations are not a full model request or hidden internals. Each block displays at most 16,000 characters; the import remains in page memory.')}</p>`;
}
export function metrics(report){const last=report.results.at(-1);return `<div class="ln-metrics"><span>${report.calls.length} ${t('次工具请求','tool calls')}</span><span>${report.calls.filter(n=>n.status==='pending').length} ${t('项等待结果','awaiting results')}</span><span>${report.calls.filter(n=>n.status==='failed').length} ${t('项工具错误','tool errors')}</span><span>${report.results.length} ${t('个结束记录','result records')}</span></div>${last?`<p class="ln-meta">${t('最后结束记录报告','Last result reports')}：${Number.isFinite(last.duration_ms)?last.duration_ms+' ms':'—'} · ${Number.isFinite(last.total_cost_usd)?'$'+last.total_cost_usd+' USD':t('费用未报告','Cost not reported')} · ${Number.isFinite(last.num_turns)?last.num_turns+' turns':t('轮数未报告','Turns not reported')}</p>`:''}`;}
