import { escapeHtml as esc } from '../util.js';
import { isEnglish } from '../i18n.js';
const t=(zh,en)=>isEnglish()?en:zh;
export const toolName=name=>({query_articles:t('搜索文章','Search articles'),read_article:t('读取文章详情','Read article details')}[name]||name||t('未知工具','Unknown tool'));
function parse(value){try{return JSON.parse(value);}catch{return value;}}
const pretty=value=>`<pre>${esc(typeof value==='string'?value:JSON.stringify(value,null,2))}</pre>`;
function callHint(call, output){
 const args=parse(call?.function?.arguments||'{}');
 const hint=call?.function?.name==='query_articles'?args?.keyword:output?.title_zh||output?.title;
 return typeof hint==='string'&&hint?` · ${esc(hint.slice(0,70))}`:'';
}
export function contextMessages(messages, turn) {
 // Resolve against the preceding assistant batch, not a global ID map: IDs may
 // be reused in later turns. Unmatched results keep an explicit generic label.
 let batch=new Map();
 return messages.map((message,i)=>{
  const calls=message.tool_calls||[];
  if(message.role==='assistant')batch=new Map(calls.map(call=>[call.id,call]));
  const call=message.role==='tool'?batch.get(message.tool_call_id):null;
  const output=message.role==='tool'?parse(message.content):null;
  let title={system:t('系统规则','System rules'),user:t('你的问题','Your question'),assistant:t('模型消息','Model message')}[message.role]||message.role;
  if(calls.length)title=t('模型请求执行工具','Model requests tools')+` · ${calls.length}`;
  if(message.role==='tool')title=call?toolName(call.function?.name)+t('的结果',' result'):t('工具结果（未匹配到调用）','Tool result (unmatched call)');
  const body=calls.length?`${message.content?pretty(message.content):''}${calls.map(item=>`<section class="ar-context-call"><b>${esc(toolName(item.function?.name))}${callHint(item)}</b>${pretty(parse(item.function?.arguments||'{}'))}</section>`).join('')}`:pretty(output??message.content??message);
  return `<details class="ar-message" data-ar-detail="message-${turn}-${i}" ${i===messages.length-1?'open':''}><summary>${i+1}. ${esc(title)}${callHint(call,output)} <small>· ${new TextEncoder().encode(JSON.stringify(message)).length.toLocaleString()} B</small></summary>${body}<details data-ar-detail="raw-message-${turn}-${i}"><summary>${t('关联 ID 与原始消息','Association IDs and raw message')}</summary>${pretty(message)}</details></details>`;
 }).join('');
}
