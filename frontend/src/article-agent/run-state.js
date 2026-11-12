// Event projection only: the server is the authority on execution.
export function newRun() { return { events:[], status:'idle', selected:-1 }; }
export function receiveEvent(state, event) {
 const terminal={final:'completed',error:'failed',cancelled:'stopped'};
 return {...state,events:[...state.events,event],status:terminal[event.type]||'running',selected:state.selected<0?0:state.selected};
}
export function foundArticles(events) {
 const articles=new Map();
 for(const event of events){
  if(event.type!=='tool_result'||!event.result||event.result.error)continue;
  const rows=Array.isArray(event.result.articles)?event.result.articles:event.name==='read_article'?[event.result]:[];
  for(const row of rows){if(!row.id)continue;const previous=articles.get(row.id)||{};articles.set(row.id,{...previous,...row,read:previous.read||event.name==='read_article'});}
 }
 return [...articles.values()];
}
export async function readEvents(response, onEvent) {
 if(!response.body)throw new Error('Missing event stream');
 const reader=response.body.getReader(),decoder=new TextDecoder();let pending='';
 function consume(block){
  if(block.length>2*1024*1024)throw new Error('Event too large');
  const data=block.split('\n').filter(line=>line.startsWith('data:')).map(line=>line.slice(5).trimStart()).join('\n');
  if(data)onEvent(JSON.parse(data));
 }
 try {
  while(true){const {value,done}=await reader.read();pending+=decoder.decode(value||new Uint8Array(),{stream:!done});pending=pending.replace(/\r\n/g,'\n');let boundary;
   while((boundary=pending.indexOf('\n\n'))>=0){consume(pending.slice(0,boundary));pending=pending.slice(boundary+2);}
   if(pending.length>2*1024*1024)throw new Error('Event too large');
   if(done){if(pending.trim())consume(pending);break;}
  }
 }finally{reader.releaseLock();}
}
