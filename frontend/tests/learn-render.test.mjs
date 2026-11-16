import test from 'node:test';
import assert from 'node:assert/strict';
Object.defineProperty(globalThis,'navigator',{value:{language:'en-US'},configurable:true});
globalThis.location={search:'?lang=en'};globalThis.localStorage={getItem:()=>null};
const {outline,nodeDetail}=await import('../src/learn/trace-view.js');
test('untrusted tool names and hostile input objects render without prototype lookup or HTML execution',()=>{
 const node={order:0,key:'n0',kind:'call',title:'toString',input:{command:{toString:1},file_path:'<img src=x onerror=bad>'},status:'pending',lines:[1],segment:0};
 const html=outline({nodes:[node]},0,200)+nodeDetail(node,{kind:'jsonl',rows:[{line:1,data:{type:'assistant'}}]});
 assert.ok(html.includes('toString'));assert.ok(html.includes('&lt;img'));assert.ok(!html.includes('<img'));
});
