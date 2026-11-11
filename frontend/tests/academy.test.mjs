import test from 'node:test';
import assert from 'node:assert/strict';
import { models, filterModels, relatedModels, staleRecord, readProgress, saveCompletion, clearProgress } from '../src/academy/catalog.js';
import { agents } from '../src/academy/agents.js';
import { lessons, lessonTrace } from '../src/academy/lessons.js';
import { inspectRequest } from '../src/academy/inspect-request.js';
test('catalog identities are unique, sourced and distinguish unverified properties',()=>{
 assert.ok(models.length>=30);assert.ok(new Set(models.map(m=>m.provider)).size>=10);assert.equal(new Set(models.map(m=>m.id)).size,models.length);
 for(const m of models){assert.match(m.source,/^https:\/\//);assert.match(m.verified_on,/^\d{4}-\d{2}-\d{2}$/);assert.ok(m.verification);assert.equal(m.pricing,null);assert.equal(m.lifecycle,'not-verified');}
 assert.ok(filterModels('claude','Anthropic','text').length>=3);assert.equal(filterModels('no-such-model').length,0);assert.equal(relatedModels('Claude Sonnet 5.5 news')[0].provider,'Anthropic');
 assert.equal(staleRecord({verified_on:'2020-01-01'},Date.UTC(2026,10,11)),true);
});
test('every agent links to a sourced lesson and every trace parses without broken associations',()=>{
 assert.ok(agents.filter(a=>a.type==='product').length>=3);assert.ok(agents.filter(a=>a.type==='pattern').length>=3);
 for(const a of agents){assert.ok(lessons.some(l=>l.id===a.lesson));assert.match(a.source,/^https:\/\//);}
 for(const lesson of lessons){const trace=lessonTrace(lesson.id);assert.ok(trace.length>=2);assert.ok(lesson.choices[lesson.answer]);for(const raw of trace){const r=inspectRequest(raw,lesson.protocol);assert.ok(r.links.every(l=>l.matches.length===1));}}
 const recovery=inspectRequest(lessonTrace('recovery')[1],'claude');assert.equal(recovery.results[0].error,true);
});
test('learning progress stores completion flags only and tolerates disabled storage',()=>{
 const values=new Map();globalThis.localStorage={getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)};
 clearProgress();assert.equal(saveCompletion('notes'),true);assert.deepEqual(readProgress(),{notes:true});clearProgress();assert.deepEqual(readProgress(),{});
 globalThis.localStorage={getItem:()=>{throw Error('denied')},setItem:()=>{throw Error('denied')},removeItem:()=>{throw Error('denied')}};
 assert.equal(saveCompletion('memory'),false);assert.deepEqual(readProgress(),{memory:true});clearProgress();
});
