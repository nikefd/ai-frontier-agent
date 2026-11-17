import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {parseTrace,projectTrace} from '../src/learn/trace-model.js';
Object.defineProperty(globalThis,'navigator',{value:{language:'zh-CN'},configurable:true});
globalThis.location={search:'?lang=zh'};
globalThis.localStorage={getItem:()=>null};
const {storySteps,storyIndex,taskStory}=await import('../src/learn/task-story.js');
const rows=parseTrace(await readFile(new URL('../public/learn/examples/search-child.jsonl',import.meta.url),'utf8')).rows;
test('guide milestones correspond to observed failure, delegation, edit and verified results',()=>{
 for(const step of storySteps)assert.ok(rows.some(row=>row.line===step.line));
 const before=projectTrace(rows.slice(0,9));assert.equal(before.calls.at(-1).status,'failed');
 const waiting=projectTrace(rows.slice(0,15));assert.equal(waiting.calls.find(n=>n.title==='Agent').status,'pending');
 const returned=projectTrace(rows.slice(0,16));assert.equal(returned.calls.find(n=>n.title==='Agent').status,'completed');
 assert.equal(projectTrace(rows.slice(0,19)).calls.at(-1).title,'Edit');
 assert.equal(projectTrace(rows.slice(0,21)).calls.at(-1).status,'completed');
 assert.equal(storyIndex(20),6);assert.equal(storyIndex(21),7);
});
test('walkthrough does not announce passing tests or expose future code before verification',()=>{
 const initial=taskStory(1,rows);assert.match(initial,/尚未运行|Not run yet/);assert.ok(!initial.includes('ls-code'));
 const edited=taskStory(19,rows);assert.match(edited,/2通过 · 5失败|2 pass · 5 fail/);assert.match(edited,/ls-code/);assert.match(edited,/normalize/);
 const verified=taskStory(21,rows);assert.match(verified,/7通过 · 0失败|7 pass · 0 fail/);
 const hostile=structuredClone(rows);hostile[17].data.message.content[0].input.old_string='<script>bad()</script>';
 const html=taskStory(19,hostile);assert.ok(!html.includes('<script>'));assert.match(html,/&lt;script&gt;/);
});
