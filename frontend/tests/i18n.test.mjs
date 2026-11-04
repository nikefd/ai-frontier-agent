import test from 'node:test';
import assert from 'node:assert/strict';
Object.defineProperty(globalThis, 'navigator', {value:{language:'en-US'},configurable:true});
globalThis.location={search:'?lang=en'};
globalThis.localStorage={getItem:()=>null};
const {resolveLanguage,uiText,uiTemplate}=await import('../src/i18n.js');
test('URL, saved preference and browser locale have predictable precedence',()=>{
 assert.equal(resolveLanguage('zh','en','en-US'),'zh');
 assert.equal(resolveLanguage('unsupported','zh','en-US'),'zh');
 assert.equal(resolveLanguage(null,null,'en-GB'),'en');
 assert.equal(resolveLanguage(null,null,'fr-FR'),'en');
});
test('templates translate UI but leave interpolated content untouched',()=>{
 assert.equal(uiText('今日速报'),'Daily briefing');
 const value='用户内容 {0} <script>unsafe()</script>';
 assert.equal(uiTemplate`共 ${value} 个用户`,`${value} users`);
 assert.equal(uiText('Unregistered content'),'Unregistered content');
});
test('every translated template preserves the original placeholder inventory',async()=>{
 const {default:catalog}=await import('../src/messages.en.json',{with:{type:'json'}});
 for(const [original,translated]of Object.entries(catalog)){
  const tokens=s=>[...s.matchAll(/\{\d+\}/g)].map(x=>x[0]).sort();
  assert.deepEqual(tokens(translated),tokens(original),original);
 }
});
