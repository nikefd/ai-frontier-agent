import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {captureCases} from '../src/learn/capture-cases.js';
const data=JSON.parse(await readFile(new URL('../public/learn/examples/http-normal.json',import.meta.url),'utf8'));
const tableIds=text=>[...text.matchAll(/^\|\s*(A\d+)\s*\|/gm)].map(m=>m[1]);
test('normal example consists of three genuine user turns with cumulative request histories',()=>{
 assert.equal(captureCases[0].kind,'normal');assert.equal(data.user_turns.length,3);assert.equal(data.exchanges.length,7);
 assert.deepEqual(data.user_turns.map(t=>t.request_indices),[[0,1,2],[3,4],[5,6]]);
 for(const turn of data.user_turns){
  const first=data.exchanges[turn.request_indices[0]];assert.equal(first.user_turn,turn.number);
  const history=JSON.stringify(first.request.messages);
  for(const earlier of data.user_turns.slice(0,turn.number))assert.ok(history.includes(earlier.user_message));
 }
 assert.ok(data.user_turns.every(t=>t.assistant_message.length>50));
});
test('normal results progress from four articles to three and a valid three-day plan',()=>{
 const [first,second,third]=data.user_turns;
 assert.deepEqual(tableIds(first.files['shortlist.md']),['A1','A3','A2','A4']);
 assert.deepEqual(tableIds(second.files['shortlist.md']),['A3','A2','A4']);
 assert.equal(third.files['shortlist.md'],second.files['shortlist.md']);
 const plan=third.files['reading-plan.md'].split('\n').filter(l=>/^\|\s*Day [123]\s*\|/.test(l)).map(l=>l.trim().slice(1,-1).split('|').map(c=>c.trim()));
 assert.equal(plan.length,3);assert.deepEqual(plan.map(row=>row[1]),['A3','A2','A4']);
 assert.ok(plan.every(row=>Number(row[3])>0&&Number(row[3])<=20&&row[4]&&row[5]));
 for(const exchange of data.exchanges){
  const blocks=exchange.request.messages.flatMap(m=>Array.isArray(m.content)?m.content:[]);
  assert.ok(blocks.filter(b=>b.type==='tool_result').every(b=>!b.is_error));
 }
 assert.equal(data.verification.source_unchanged,true);
});
