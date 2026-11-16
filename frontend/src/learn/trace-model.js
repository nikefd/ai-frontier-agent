// Claude Code trace projection. No IO, DOM, execution or persistence.
export const TRACE_LIMIT=5*1024*1024;
export function parseTrace(source) {
 if(new TextEncoder().encode(source).length>TRACE_LIMIT)throw new Error('Trace limit: 5 MiB');
 const trimmed=source.trim();if(!trimmed)throw new Error('Empty trace');
 let rows;
 if(trimmed.startsWith('[')) {const values=JSON.parse(trimmed);rows=values.map((data,i)=>({line:i+1,data}));}
 else rows=source.split('\n').flatMap((raw,i)=>{if(!raw.trim())return [];try{return [{line:i+1,data:JSON.parse(raw)}];}catch{return [{line:i+1,error:'Invalid JSON',raw}];}});
 if(rows.length>10000)throw new Error('Trace limit: 10,000 records');
 if(!rows.some(row=>['assistant','user','system','result','stream_event'].includes(row.data?.type)))throw new Error('Not a Claude Code trace');
 return {rows,kind:trimmed.startsWith('[')?'array':'jsonl'};
}
const printable=value=>typeof value==='string'?value:JSON.stringify(value??'',null,2);
export function projectTrace(rows) {
 const nodes=[],diagnostics=[],results=[],calls=new Map(),snapshots=new Map(),parents=new Map();let segment=0,session='',model='';
 function push(node){node.order=nodes.length;node.key='n'+node.order;node.lines=[node.line];nodes.push(node);return node;}
 for(const row of rows){
  if(row.error){diagnostics.push({line:row.line,message:row.error});continue;}
  const record=row.data;if(!record||typeof record!=='object'){diagnostics.push({line:row.line,message:'Record is not an object'});continue;}
  const scope=typeof record.parent_tool_use_id==='string'?record.parent_tool_use_id:'';
  if(record.type==='system'&&record.subtype==='init'){session=typeof record.session_id==='string'?record.session_id:session;model=typeof record.model==='string'?record.model:model;}
  const base={line:row.line,segment,scope,parentId:scope,session};
  if(record.type==='system'&&record.subtype==='init')push({...base,kind:'config',title:'session init',text:printable({model,tools:record.tools}),status:'observed'});
  if(['assistant','user'].includes(record.type)){
   const message=record.message||{},blocks=typeof message.content==='string'?[{type:'text',text:message.content}]:Array.isArray(message.content)?message.content:[];
   blocks.forEach((block,i)=>{
    if(!block||typeof block!=='object')return;
    const blockKey=block.type==='tool_use'&&typeof block.id==='string'?`tool:${block.id}`:`${block.type}:${i}`;
    const snapshot=typeof message.id==='string'?`${segment}:${scope}:${message.id}:${blockKey}`:null;
    if(block.type==='tool_result'){
     const id=typeof block.tool_use_id==='string'?block.tool_use_id:'';const group=id?calls.get(`${segment}:${scope}:${id}`)||[]:[];
     if(group.length===1){const node=group[0];node.status=block.is_error?'failed':'completed';node.output=printable(block.content);node.lines.push(row.line);}
     else {push({...base,kind:'unmatched',title:'Unmatched tool result',text:printable(block.content),status:block.is_error?'failed':'unknown'});diagnostics.push({line:row.line,message:group.length?'Duplicate call ID; result not associated':'Tool result without a matching call'});}
     return;
    }
    if(!['text','tool_use'].includes(block.type))return;
    const old=snapshot?snapshots.get(snapshot):null;
    if(old&&(block.type==='tool_use'||printable(block.text).startsWith(old.text)||old.text.startsWith(printable(block.text)))){old.lines.push(row.line);if(block.type==='text'){if(printable(block.text).length>=old.text.length)old.text=printable(block.text);}else old.input=block.input;return;}
    const node=push(block.type==='tool_use'?{...base,kind:'call',title:typeof block.name==='string'?block.name:'Unknown tool',id:typeof block.id==='string'?block.id:'',input:block.input,status:'pending'}:{...base,kind:'message',title:record.type,text:printable(block.text),status:record.is_api_error_message===true?'failed':'observed'});
    if(snapshot)snapshots.set(snapshot,node);
    if(node.kind==='call'&&node.id){
     const key=`${segment}:${scope}:${node.id}`;const group=calls.get(key)||[];group.push(node);calls.set(key,group);
     const parentKey=`${segment}:${node.id}`;const candidates=parents.get(parentKey)||[];candidates.push(node);parents.set(parentKey,candidates);
    }
   });
  }else if(record.type==='result'){
   const failed=record.is_error===true||typeof record.subtype==='string'&&record.subtype.startsWith('error');
   results.push({...record,line:row.line,segment});push({...base,kind:'final',title:failed?'error':'result',text:printable(record.result||record.errors||''),status:failed?'failed':'completed'});segment++;
  }
 }
 for(const node of nodes){if(!node.parentId)continue;const group=parents.get(`${node.segment}:${node.parentId}`)||[];if(group.length===1&&group[0]!==node)node.parentKey=group[0].key;else diagnostics.push({line:node.line,message:'Parent tool call missing or ambiguous'});}
 return {nodes,diagnostics,results,session,model,calls:nodes.filter(n=>n.kind==='call')};
}
export function traceTree(nodes) {
 const byKey=new Map(nodes.map(node=>[node.key,{...node,children:[]}])),roots=[],finished=new Set(),cyclic=new Set();
 for(const node of byKey.values()){
  let cursor=node;const path=[],positions=new Map();
  while(cursor&&!finished.has(cursor.key)){
   if(positions.has(cursor.key)){path.slice(positions.get(cursor.key)).forEach(key=>cyclic.add(key));break;}
   positions.set(cursor.key,path.length);path.push(cursor.key);cursor=byKey.get(cursor.parentKey);
  }
  path.forEach(key=>finished.add(key));
 }
 for(const node of byKey.values()){
  const parent=byKey.get(node.parentKey);
  if(parent&&!cyclic.has(node.key))parent.children.push(node);else roots.push(node);
 }
 return roots;
}
