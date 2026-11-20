import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {requestGuides,comparisonGuides} from '../src/learn/http-reading-guide.js';
const load=async kind=>JSON.parse(await readFile(new URL(`../public/learn/examples/http-${kind}.json`,import.meta.url),'utf8'));
const responseCalls=e=>e.response_events.filter(v=>v.content_block?.type==='tool_use').map(v=>v.content_block);
const results=e=>e.request.messages.flatMap(m=>Array.isArray(m.content)?m.content:[]).filter(b=>b.type==='tool_result');
test('reading labels cover all actual exchanges and delegation remains in the child scope',async()=>{
 const repair=await load('repair'),skill=await load('skill');
 assert.equal(requestGuides[repair.case_id].length,repair.exchanges.length);assert.equal(requestGuides[skill.case_id].length,skill.exchanges.length);
 assert.deepEqual(responseCalls(repair.exchanges[0]).map(b=>b.name),['Read','Read','Read','Bash']);
 assert.deepEqual(responseCalls(repair.exchanges[1]).map(b=>b.name),['Agent']);
 assert.equal(repair.exchanges[2].scope,'child');assert.equal(results(repair.exchanges[2]).length,0);
 assert.deepEqual(responseCalls(repair.exchanges[4]).map(b=>b.name),['Edit']);
 assert.deepEqual(responseCalls(skill.exchanges[2]).map(b=>b.name),['Read','Read','Read']);
 assert.match(JSON.stringify(results(skill.exchanges[4])),/fail 5/);
});
test('tool comparison follows actual call IDs into the next main request',async()=>{
 const data=await load('repair'),route=comparisonGuides.find(g=>g.id==='tools');
 const proposed=responseCalls(data.exchanges[route.points[0].index]),returned=results(data.exchanges[route.points[1].index]);
 assert.equal(proposed.length,4);
 for(const call of proposed)assert.ok(returned.some(result=>result.tool_use_id===call.id));
 const delegation=responseCalls(data.exchanges[1])[0];assert.ok(results(data.exchanges[4]).some(r=>r.tool_use_id===delegation.id));
});
test('Skill comparison distinguishes availability, invocation and body injection',async()=>{
 const data=await load('skill'),route=comparisonGuides.find(g=>g.id==='skill');
 assert.equal(route.points[0].format,'response');assert.equal(route.points[1].format,'request');
 assert.ok(data.exchanges[0].request.tools.some(t=>t.name==='Skill'));
 assert.deepEqual(responseCalls(data.exchanges[0]).map(c=>c.name),['Skill']);
 const body='A failed test is an observed finding, not permission to fix code.';
 assert.ok(!JSON.stringify(data.exchanges[0].request.messages).includes(body));
 assert.ok(JSON.stringify(data.exchanges[1].request.messages).includes(body));
});
