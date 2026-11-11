import { readTrace, textValue } from './read-trace.js';
import { traceAdapter } from './trace-adapters.js';
export function analyzeTrace(source, format='auto') {
 const parsed=readTrace(source,format), adapter=traceAdapter(parsed.format), diagnostics=[];
 if(parsed.detected&&parsed.detected!==parsed.format)diagnostics.push({line:1,message:'Selected format differs from detected format: '+parsed.detected});
 parsed.records.forEach(record=>{if(record.error)diagnostics.push({line:record.line,message:record.error});else adapter.accept(record);});
 const report={...parsed,...adapter.finish(),diagnostics};
 const calls=report.nodes.filter(n=>n.kind==='call'),results=report.nodes.filter(n=>n.kind==='result');
 const key=node=>JSON.stringify([node.scope,parsed.format==='claude-code'?0:node.turn,node.callId]);
 const groups=new Map();
 for(const node of [...calls,...results]){const id=key(node);if(!groups.has(id))groups.set(id,{calls:[],results:[]});groups.get(id)[node.kind==='call'?'calls':'results'].push(node);}
 report.links=calls.map(call=>{const group=groups.get(key(call));return {call,ambiguous:group.calls.length>1,results:call.callId&&group.calls.length===1?group.results.filter(r=>r.order>call.order):[]};});
 for(const link of report.links){
  if(!link.call.callId)diagnostics.push({line:link.call.lines[0],message:'Call has no ID; results cannot be reliably associated.'});
  if(link.ambiguous)diagnostics.push({line:link.call.lines[0],message:'Duplicate call ID in the same scope; association withheld: '+link.call.callId});
  else if(!link.results.length)diagnostics.push({line:link.call.lines[0],message:'No later result for call '+link.call.callId});
 }
 for(const result of results){const group=groups.get(key(result));if(!result.callId||group.calls.length!==1||group.calls[0].order>=result.order)diagnostics.push({line:result.line||result.lines[0],message:group.calls.length>1?'Ambiguous result: duplicate preceding call IDs.':'Orphan result: no preceding matching call in this scope.'});}

 report.failures=results.filter(r=>r.error);
 report.testRuns=report.links.filter(l=>/\b(?:pytest|vitest|cargo test|go test|npm(?:\s+--prefix\s+\S+)?\s+(?:run\s+)?test|node\s+--test)\b/.test(textValue(l.call.arguments)||l.call.text||''));
 report.changes=report.nodes.filter(n=>n.kind==='file_change');
 report.compactions=report.nodes.filter(n=>n.kind==='compaction');
 report.approvals=report.nodes.filter(n=>n.kind==='approval');
 return report;
}
export function priorEvidence(report,node) {
 const prior=report.nodes.filter(n=>n.order<node.order&&['message','result','context','compaction'].includes(n.kind));
 const lastCompaction=prior.findLastIndex(n=>n.kind==='compaction');
 return {records:prior,compaction:lastCompaction>=0?prior[lastCompaction]:null};
}
