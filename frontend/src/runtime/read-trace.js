export const TRACE_FORMATS = ['codex-exec', 'codex-rollout', 'claude-code'];
const MAX_BYTES = 8 * 1024 * 1024;
export function readTrace(source, selected = 'auto') {
  if (new TextEncoder().encode(source).length > MAX_BYTES) throw new Error('Trace limit: 8 MiB');
  if (!source.trim()) throw new Error('Paste JSONL or import a trace file.');
  let records, sourceKind='jsonl';
  if (source.trim().startsWith('[')) {
    sourceKind='json-array';
    const values = JSON.parse(source);
    if (!Array.isArray(values)) throw new Error('Expected a JSON array');
    records = values.map((data,index)=>({line:index+1,data}));
  } else records = source.split(/\r?\n/).map((raw,index)=>({raw,line:index+1})).filter(r=>r.raw.trim()).map(r=>{
    try { return {...r,data:JSON.parse(r.raw)}; } catch { return {...r,error:'Invalid JSON on this line'}; }
  });
  if (records.length > 20000) throw new Error('Trace limit: 20,000 records');
  records = records.map(r => r.data && typeof r.data==='object' && !Array.isArray(r.data) ? r : {...r,error:r.error||'Record must be an object'});
  const data=records.filter(r=>!r.error).map(r=>r.data);
  const detected=data.some(d=>['session_meta','response_item','turn_context','event_msg','compacted'].includes(d.type))?'codex-rollout':data.some(d=>/^thread\.|^turn\.|^item\./.test(typeof d.type==='string'?d.type:''))?'codex-exec':data.some(d=>['assistant','user','result','stream_event'].includes(d.type)||d.type==='system'&&d.subtype==='init')?'claude-code':null;
  const format=selected==='auto'?detected:selected;
  if(!TRACE_FORMATS.includes(format))throw new Error('Unrecognized trace format; choose a supported format.');
  return {format,detected,records,sourceKind,bytes:new TextEncoder().encode(source).length};
}
export const textValue = value => typeof value==='string'?value:JSON.stringify(value??null,null,2);
export const valueString = (value,fallback='') => typeof value==='string'?value:fallback;
export const usageValue = value => {
  if(!value||typeof value!=='object'||Array.isArray(value))return {};
  return Object.fromEntries(Object.entries(value).filter(([,v])=>typeof v==='number'&&Number.isFinite(v)&&v>=0));
};
