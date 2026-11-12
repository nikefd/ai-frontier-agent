import test from 'node:test';
import assert from 'node:assert/strict';
import {newRun,receiveEvent,foundArticles,readEvents} from '../src/article-agent/run-state.js';
test('only real tool output contributes article cards; reads update the same article',()=>{
 const events=[{type:'model_response',message:{content:'invented article'}},{type:'tool_result',name:'query_articles',result:{articles:[{id:'a',title:'Agent',url:'https://example.org'}]}},{type:'tool_result',name:'read_article',result:{id:'a',title:'Agent memory',summary:'evidence'}},{type:'tool_result',result:{error:'failed',articles:[{id:'bad'}]}}];
 const articles=foundArticles(events);assert.equal(articles.length,1);assert.equal(articles[0].read,true);assert.equal(articles[0].url,'https://example.org');assert.equal(articles[0].title,'Agent memory');
});
test('event parser handles UTF8 and SSE records split across arbitrary chunk boundaries',async()=>{
 const wire='data: '+JSON.stringify({type:'tool_result',summary:'真实结果'})+'\r\n\r\ndata: '+JSON.stringify({type:'final',content:'done'})+'\n\n';
 const bytes=new TextEncoder().encode(wire);let offset=0;const events=[];
 const body=new ReadableStream({pull(controller){if(offset>=bytes.length){controller.close();return;}controller.enqueue(bytes.slice(offset,offset+1));offset++;}});
 await readEvents({body},event=>events.push(event));assert.equal(events.length,2);assert.equal(events[0].summary,'真实结果');
 const state=events.reduce(receiveEvent,newRun());assert.equal(state.status,'completed');assert.equal(state.events.length,2);
});
