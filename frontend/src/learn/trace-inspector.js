import {escapeHtml as esc} from '../util.js';
import {projectTrace} from './trace-model.js';
import {t} from './trace-view.js';
const pretty=value=>JSON.stringify(value??null,null,2);
const bytes=value=>new TextEncoder().encode(pretty(value)).length;
const preview=value=>String(typeof value==='string'?value:pretty(value)).replace(/\s+/g,' ').slice(0,110);
const code=value=>`<pre>${esc(typeof value==='string'?value:pretty(value))}</pre>`;
export const toolNotes={
 Read:['读取文件，把文本放进工具反馈；不会修改文件。','Reads a file into a tool result without modifying it.'],
 Bash:['请求本机运行命令。模型写出命令，执行器才负责运行并返回结果。','Requests a local command. The model proposes it; the executor runs it and returns output.'],
 Agent:['把指令交给子任务；报告经同一个调用的工具结果返回主任务。','Delegates instructions; the child report returns through this call’s tool result.'],
 Edit:['用 old_string 匹配原文，再替换成 new_string；写入成功还需要测试验证。','Matches old_string and replaces it with new_string; a successful write still needs tests.'],
};
export function inspectCalls(rows,state){
 const report=projectTrace(rows),calls=report.calls;
 const selected=calls.find(n=>n.line===state.line)||calls.at(-1);
 return `<div class="li-split"><aside class="li-list"><h3>${t('已发生的工具调用','Observed tool calls')} <small>${calls.length}</small></h3>${calls.map(n=>`<button data-inspect-action="call-${n.line}" data-inspect-line="${n.line}" aria-pressed="${n===selected}"><b>${esc(n.title)}</b><span>${n.parentKey?t('子任务','Child'):t('主任务','Main')} · L${n.lines.join(', L')}</span><small>${esc(preview(n.input.command||n.input.file_path||n.input.description||n.input))}</small><em class="li-${n.status}">${status(n.status)}</em></button>`).join('')||`<p>${t('本步骤尚未调用工具。点“读文件”开始。','No tool calls yet. Advance to “Read”.')}</p>`}</aside><article class="li-detail">${selected?callDetail(selected):`<h3>${t('模型还没有请求工具','No tool requested yet')}</h3><p>${t('工具调用和工具执行是两件事：请求先出现，收到结果后才能知道执行状态。','A tool request is distinct from execution: the call appears first; its result establishes the outcome.')}</p>`}</article></div>`;
}
function status(value){return ({pending:t('等待结果','Awaiting result'),completed:t('已返回','Returned'),failed:t('执行失败','Failed')})[value]||value;}
export function readableToolOutput(value){
 if(typeof value!=='string')return pretty(value);
 try{const blocks=JSON.parse(value);if(Array.isArray(blocks)&&blocks.every(b=>b&&b.type==='text'&&typeof b.text==='string'))return blocks.map(b=>b.text).join('\n\n');}catch{/* Most results are already plain text. */}
 return value;
}
function parameters(input){return `<dl class="li-params">${Object.entries(input||{}).map(([key,value])=>`<dt>${esc(key)}</dt><dd>${code(typeof value==='string'?value:pretty(value))}</dd>`).join('')}</dl>`;}
function messageBlocks(blocks){
 return blocks.map(b=>`<section><h4>${esc(b.type)}${b.name?' · '+esc(b.name):''}</h4>${b.type==='text'?code(b.text):b.type==='tool_use'?parameters(b.input):b.type==='tool_result'?code(readableToolOutput(typeof b.content==='string'?b.content:pretty(b.content))):code(b)}</section>`).join('');
}
function callDetail(n){
 return `<header><span class="li-tag">${esc(n.title)} · ${status(n.status)}</span><h3>${esc(n.input.description||n.input.file_path||n.title)}</h3><p>${Object.hasOwn(toolNotes,n.title)?t(...toolNotes[n.title]):t('以下参数与结果来自实际记录。','Parameters and results below come from the capture.')}</p></header><section><h4>${t('① 模型请求执行什么','① What the model requests')}</h4>${parameters(n.input)}</section><section><h4>${t('② 执行器实际返回什么','② What the executor returns')}</h4>${n.status==='pending'?`<p class="li-wait">${t('此时还没有结果。后续步骤才会收到反馈。','No result yet. Feedback arrives in a later step.')}</p>`:code(readableToolOutput(n.output))}</section><details><summary>${t('核对关联关系','Verify association')}</summary>${code({tool:n.title,call_id:n.id,parent_call_id:n.parentId||null,segment:n.segment+1,reviewed_lines:n.lines})}</details>`;
}
export function contextRows(rows,scope='main'){
 return rows.filter(row=>{const r=row.data;return r&&['assistant','user'].includes(r.type)&&(scope==='child'?Boolean(r.parent_tool_use_id):!r.parent_tool_use_id);}).map(row=>{
  const content=row.data.message?.content||[];
  const kind=content.some(b=>b.type==='tool_result')?'tool_result':content.some(b=>b.type==='tool_use')?'tool_use':'text';
  return {...row,kind,byteLength:bytes(content),content};
 });
}
function contextLabel(row){return row.kind==='tool_result'?t('工具反馈 · user封装','Tool result · user envelope'):row.kind==='tool_use'?t('assistant · 工具请求','assistant · tool request'):row.data.type==='user'?t('user · 子任务指令','user · child instructions'):t('assistant · 文本','assistant · text');}
export function inspectContext(rows,state){
 const scope=state.scope||'main',messages=contextRows(rows,scope),chosen=messages.find(r=>r.line===state.line)||messages.at(-1);
 const categories=['text','tool_use','tool_result'].map(kind=>({kind,total:messages.filter(r=>r.kind===kind).reduce((sum,r)=>sum+r.byteLength,0)}));
 const total=categories.reduce((sum,k)=>sum+k.total,0);
 const init=rows.find(r=>r.data?.type==='system'&&r.data.subtype==='init')?.data;
 return `<section class="li-context"><div class="li-scope">${['main','child'].map(value=>`<button data-inspect-action="scope-${value}" data-inspect-scope="${value}" aria-pressed="${scope===value}">${value==='main'?t('主任务消息','Main messages'):t('Explore 子任务消息','Explore child messages')}</button>`).join('')}<small>${messages.length} ${t('条可见记录','visible records')} · ${total.toLocaleString()} B</small></div><div class="li-bytebar" aria-label="${t('可见记录内容字节占比，不是API上下文占比','Bytes of visible record content, not API context composition')}">${categories.filter(k=>k.total).map(k=>`<span class="li-kind-${k.kind}" title="${k.kind}: ${k.total.toLocaleString()} B" style="flex:${k.total}">${k.kind}</span>`).join('')}</div><div class="li-legend">${categories.map(k=>`<span><i class="li-kind-${k.kind}"></i>${k.kind} · ${k.total.toLocaleString()} B</span>`).join('')}</div><p class="li-note">${t('按当前步骤以前保留的消息块序列化字节统计，包含调用和返回；不是某一轮实际发送的请求，也不等于Token用量。','Serialized bytes of retained message blocks up to this step, including calls and results. This is not a request sent in any particular turn or a token count.')}</p><div class="li-split"><aside class="li-list"><h3>${t('消息块序列','Message block sequence')}</h3>${messages.map(r=>`<button data-inspect-action="message-${r.line}" data-inspect-line="${r.line}" aria-pressed="${r===chosen}"><b>L${r.line} · ${contextLabel(r)}</b><span>${r.byteLength.toLocaleString()} B · ${t('运行段','Segment')} ${r.data.capture_segment||1}</span><small>${esc(preview(r.content))}</small></button>`).join('')||`<p>${t('当前步骤还没有该范围的消息。','No messages in this scope at this step.')}</p>`}</aside><article class="li-detail">${chosen?`<h3>L${chosen.line} · ${contextLabel(chosen)}</h3>${chosen.kind==='tool_result'?`<p class="li-note">${t('这里的user是CLI日志承载工具反馈的消息类型，不是你又发了一条指令。用tool_use_id可以关联回前一条assistant工具请求。','Here user is the CLI message envelope for tool feedback, not another instruction from you. tool_use_id links it back to the assistant tool request.')}</p>`:''}${messageBlocks(chosen.content)}<details><summary>${t('原始消息块JSON','Raw message blocks JSON')}</summary>${code(chosen.content)}</details>`:`<p>${t('子任务创建后才能看到它的指令与读取结果。','Child instructions and read results appear after delegation.')}</p>`}</article></div><details class="li-config"><summary>${t('运行配置 / System / Tools / Skills：哪些能看到？','Runtime / System / Tools / Skills: what is observable?')}</summary><dl><dt>${t('模型','Model')}</dt><dd>${esc(init?.model||'—')}</dd><dt>${t('初始化工具名','Tools listed at initialization')}</dt><dd>${esc((init?.tools||[]).join(', '))}</dd></dl><p>${t('初始化列出 Task，而实际委派调用名为 Agent；原记录保留了这个差异。System初始化事件是配置元数据，不是system提示词。','Initialization lists Task while delegation is named Agent. The capture preserves this difference. A system init event is runtime metadata, not a system prompt.')}</p><p>${t('这份公开CLI采集没有保留完整system提示词、工具schema、Skill定义或完整API请求。当前已发生的调用中是否出现Skill，可从调用列表核对；不能据此推断整个CLI未加载任何Skill。','This public CLI capture does not retain the complete system prompt, tool schemas, Skill definitions or full API requests. Inspect calls for observed Skill use; their absence does not establish that the CLI loaded no Skills.')}</p></details></section>`;
}
export function inspectCode(rows,artifacts){
 const edit=projectTrace(rows).calls.find(n=>n.title==='Edit');
 const verified=rows.some(r=>r.line===21),resumed=rows.some(r=>r.line===28);
 return `<section class="li-code"><h3>${t('从改动到验证，分开核对','Check the change and verification separately')}</h3><p>${t('本案例只修改 search.mjs。原有测试与规则没有修改；续问没有新增编辑。以下内容随回放推进出现。','This case changes only search.mjs. Original tests and rules stay unchanged; resume adds no edits. Evidence appears as replay advances.')}</p>${edit?`<div class="ls-code"><div><section><h4>${t('修改前 · old_string','Before · old_string')}</h4>${code(edit.input.old_string)}</section><section><h4>${t('修改后 · new_string','After · new_string')}</h4>${code(edit.input.new_string)}</section></div></div><p>${edit.status==='pending'?t('Edit已请求，尚未收到写入结果。','Edit requested; write result not yet observed.'):t('Edit返回成功。是否正确，还要看下面的测试。','Edit returned successfully. Correctness still requires the tests below.')}</p>`:`<p class="li-wait">${t('还没有编辑。推进到“修改代码”查看实际替换。','No edit yet. Advance to “Edit” to inspect the replacement.')}</p>`}${artifacts?`<div class="li-checks">${[[9,'before_tests','修改前：2通过 / 5失败','Before: 2 pass / 5 fail'],[21,'after_tests','修改后：7通过','After: 7 pass'],[28,'followup_tests','续问复核：7通过','Resume: 7 pass']].map(([line,key,zh,en])=>`<details ${line===21&&verified?'open':''}><summary>${t(zh,en)} · ${rows.some(r=>r.line===line)?t('已观测','observed'):t('尚未发生','not observed yet')}</summary>${rows.some(r=>r.line===line)?code(artifacts[key]):`<p>${t('请先推进回放。','Advance the replay first.')}</p>`}</details>`).join('')}${edit&&edit.status!=='pending'?`<details><summary>${t('独立采集的git diff','Independently captured git diff')}</summary>${code(artifacts.diff)}</details>`:''}</div>`:''}<p class="li-note">${t('测试覆盖中文检索、Unicode、去重、无效行、空查询与不改原数据。空白ID、字段类型、性能和大输入等边界没有被这7项测试验证。','Tests cover translated search, Unicode, deduplication, malformed rows, empty queries and immutability. Whitespace IDs, field types, performance and large inputs are outside these 7 tests.')}${resumed?' '+t('续问已完成，源码差异保持不变。','Resume is complete with the source diff unchanged.'):''}</p></section>`;
}
export function bindInspection(root,onChange){
 root.querySelectorAll('[data-inspect-tab]').forEach(b=>b.onclick=()=>onChange({tab:b.dataset.inspectTab,line:Number(b.dataset.callLine)||0}));
 root.querySelectorAll('[data-inspect-line]').forEach(b=>b.onclick=()=>onChange({line:Number(b.dataset.inspectLine)}));
 root.querySelectorAll('[data-inspect-scope]').forEach(b=>b.onclick=()=>onChange({scope:b.dataset.inspectScope,line:0}));
}
