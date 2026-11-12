import test from 'node:test';
import assert from 'node:assert/strict';
Object.defineProperty(globalThis,'navigator',{value:{language:'zh-CN'},configurable:true});
globalThis.location={search:'?lang=zh'};
globalThis.localStorage={getItem:()=>null};
const {contextMessages}=await import('../src/article-agent/context-view.js');
test('context headings show tool names and search terms while raw IDs remain inspectable',()=>{
 const messages=[{role:'assistant',tool_calls:[{id:'call_long_123',function:{name:'query_articles',arguments:'{"keyword":"Agent"}'}}]},{role:'tool',tool_call_id:'call_long_123',content:'{"articles":[],"showing":0}'}];
 const html=contextMessages(messages,3);
 const headings=[...html.matchAll(/<summary>(.*?)<\/summary>/g)].map(match=>match[1]);
 assert.ok(headings.some(title=>title.includes('搜索文章的结果')&&title.includes('Agent')));
 assert.ok(headings.every(title=>!title.includes('call_long_123')));
 assert.ok(html.includes('call_long_123'));
 assert.ok(html.includes('&quot;articles&quot;: []'));
});
test('reused IDs resolve within the preceding assistant batch; unknown results stay unmatched',()=>{
 const html=contextMessages([{role:'assistant',tool_calls:[{id:'same',function:{name:'query_articles',arguments:'{}'}}]},{role:'tool',tool_call_id:'same',content:'{}'},{role:'assistant',tool_calls:[{id:'same',function:{name:'read_article',arguments:'{}'}}]},{role:'tool',tool_call_id:'same',content:'{"title":"<img onerror=bad>"}'},{role:'tool',tool_call_id:'unknown',content:'{}'}],2);
 assert.ok(html.includes('搜索文章的结果'));
 assert.ok(html.includes('读取文章详情的结果'));
 assert.ok(html.includes('工具结果（未匹配到调用）'));
 assert.ok(!html.includes('<img'));
 assert.ok(html.includes('&lt;img onerror=bad&gt;'));
});
