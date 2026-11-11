import { textValue, valueString as str, usageValue } from './read-trace.js';
const array=value=>Array.isArray(value)?value:[];
export function traceAdapter(format) {
 const nodes=[], lookup=new Map(), metadata={}, usage={};
 let model='', usageSource=null, finalStatus='', turn=0;
 function add(record,kind,fields={}) {
  const node={id:'event-'+nodes.length,kind,order:nodes.length,lines:[record.line],timestamp:str(record.data.timestamp||record.data._captured_at),scope:str(record.data.parent_tool_use_id,'main'),turn,...fields};nodes.push(node);return node;
 }
 function item(record,item) {
  const id=str(item.id,'line-'+record.line), key='exec:'+turn+':'+id;
  const previous=lookup.get(key);
  const fields={name:str(item.type,'unknown'),status:str(item.status),details:item};
  if(item.type==='command_execution')Object.assign(fields,{name:'shell',text:str(item.command),arguments:{command:item.command}});
  else if(item.type==='mcp_tool_call')Object.assign(fields,{name:[item.server,item.tool].filter(v=>typeof v==='string').join('/'),arguments:item.arguments});
  else if(item.type==='file_change')Object.assign(fields,{text:textValue(item.changes),changes:array(item.changes)});
  else Object.assign(fields,{text:str(item.text)||textValue(item)});
  const kind=['command_execution','mcp_tool_call','web_search'].includes(item.type)?'call':item.type==='file_change'?'file_change':item.type==='agent_message'?'message':item.type==='reasoning'?'summary':'unknown';
  const node=previous||add(record,kind,{callId:id,identityKind:'cli-item',...fields});
  if(previous){Object.assign(node,fields);node.lines.push(record.line);}
  lookup.set(key,node);
  if(record.data.type==='item.completed' && kind==='call') {
   const resultKey=key+':result', resultFields={callId:id,identityKind:'cli-item',name:node.name,status:str(item.status),exitCode:typeof item.exit_code==='number'?item.exit_code:null,text:typeof item.aggregated_output==='string'?item.aggregated_output:textValue(item.result??item.error??null),error:item.status==='failed'||typeof item.exit_code==='number'&&item.exit_code!==0,details:item};
   if(lookup.has(resultKey)){Object.assign(lookup.get(resultKey),resultFields);lookup.get(resultKey).lines.push(record.line);}
   else lookup.set(resultKey,add(record,'result',resultFields));
  }
 }
 function claudeMessage(record,d) {
  const m=d.message||{}, messageId=str(m.id,str(d.uuid,'line-'+record.line));
  const scope=str(d.parent_tool_use_id,'main');
  for(const [index,block] of array(m.content).entries()) {
   if(!block||typeof block!=='object')continue;
   const key='claude:'+scope+':'+messageId+':'+index;
   const fields=block.type==='tool_use'?{callId:str(block.id),name:str(block.name,'unknown'),arguments:block.input,status:'requested',details:block}:block.type==='tool_result'?{callId:str(block.tool_use_id),text:textValue(block.content),error:block.is_error===true,status:block.is_error?'failed':'returned',details:block}:block.type==='text'?{role:str(m.role,str(d.type)),text:str(block.text),details:block}:null;
   if(fields&&d.type==='assistant'){fields.messageId=messageId;fields.reportedUsage=usageValue(m.usage);}
   if(!fields)continue; // Thinking/signatures are retained only as original records.
   const kind=block.type==='tool_use'?'call':block.type==='tool_result'?'result':d.is_api_error_message?'error':'message';
   if(lookup.has(key)){Object.assign(lookup.get(key),fields);lookup.get(key).lines.push(record.line);}else lookup.set(key,add(record,kind,fields));
  }
  if(m.model&&!d.is_api_error_message)model=str(m.model);
  if(d.type==='assistant'){metadata.assistantMessageIds=[...new Set([...(metadata.assistantMessageIds||[]),scope+':'+messageId])];}
  if(d.type==='assistant'&&m.usage)metadata.messageUsage={...(metadata.messageUsage||{}),[scope+':'+messageId]:usageValue(m.usage)};
 }
 function rollout(record,d) {
  const p=d.payload||{};
  if(d.type==='session_meta'){Object.assign(metadata,{session:p.id,cwd:p.cwd,cliVersion:p.cli_version,source:p.source});add(record,'context',{name:'Session metadata',details:p});}
  else if(d.type==='turn_context'){turn++;if(p.model)model=str(p.model);add(record,'context',{name:'Turn settings',details:p});}
  else if(d.type==='compacted'||d.type==='event_msg'&&p.type==='context_compacted')add(record,'compaction',{name:'Context compaction',details:p});
  else if(d.type==='response_item') {
   if(['function_call','custom_tool_call'].includes(p.type))add(record,'call',{callId:str(p.call_id),name:str(p.name,'unknown'),arguments:p.arguments??p.input,status:'requested',details:p});
   else if(['function_call_output','custom_tool_call_output'].includes(p.type))add(record,'result',{callId:str(p.call_id),text:textValue(p.output),status:'returned',details:p});
   else if(p.type==='message')add(record,'message',{role:str(p.role),text:array(p.content).map(c=>str(c?.text)).filter(Boolean).join('\n'),details:p});
   else add(record,'unknown',{name:str(p.type,'response_item'),details:p});
  } else if(d.type==='event_msg'&&p.type==='token_count') {
   const totals=p.info?.total_token_usage;
   if(totals){Object.assign(usage,usageValue(totals));usageSource=record.line;metadata.usageSemantics='cumulative';}
  } else add(record,'observation',{name:str(p.type,str(d.type)),details:p});
 }
 return {
  accept(record) {
   const d=record.data;
   if(format==='codex-exec') {
    if(d.type==='thread.started'){metadata.session=d.thread_id;add(record,'status',{name:d.type});}
    else if(d.type==='turn.started'){turn++;add(record,'status',{name:d.type});}
    else if(['item.started','item.updated','item.completed'].includes(d.type))item(record,d.item||{});
    else if(['turn.completed','turn.failed'].includes(d.type)){finalStatus=d.type;if(d.usage){for(const k of Object.keys(usage))delete usage[k];Object.assign(usage,usageValue(d.usage));usageSource=record.line;metadata.usageSemantics='last-turn';}add(record,'status',{name:d.type,details:d});}
    else add(record,d.type==='error'?'error':'unknown',{name:str(d.type,'unknown'),text:textValue(d.message||d.error||d),details:d});
   } else if(format==='codex-rollout')rollout(record,d);
   else {
    if(d.type==='system'&&d.subtype==='init'){Object.assign(metadata,{session:d.session_id,cwd:d.cwd,tools:d.tools,permissionMode:d.permissionMode,cliVersion:d.claude_code_version});model=str(d.model);add(record,'context',{name:'CLI initialization',details:d});}
    else if(d.type==='assistant'||d.type==='user'){claudeMessage(record,d);}
    else if(d.type==='result'){finalStatus=d.is_error?'is_error=true; subtype='+str(d.subtype):str(d.subtype);Object.assign(usage,usageValue(d.usage));usageSource=record.line;metadata.usageSemantics='result-summary';Object.assign(metadata,{cost:d.total_cost_usd,durationMs:d.duration_ms,numTurns:d.num_turns,permissionDenials:d.permission_denials});add(record,d.is_error?'error':'status',{name:d.is_error?'result · is_error=true':str(d.subtype,'result'),text:str(d.result),details:d});for(const denied of array(d.permission_denials))add(record,'approval',{name:str(denied.tool_name,'Permission denied'),callId:str(denied.tool_use_id),arguments:denied.tool_input,status:'denied',details:denied});}
    else if(d.type==='system'&&/compact/.test(str(d.subtype)))add(record,'compaction',{name:str(d.subtype),details:d});
    else if(d.type==='system'&&d.subtype==='permission_denied')add(record,'approval',{name:'Permission denied',status:'denied',details:d});
    else add(record,'observation',{name:str(d.type,'unknown'),details:d});
   }
  },
  finish(){return {nodes,metadata,usage,usageSource,model,finalStatus};},
 };
}
