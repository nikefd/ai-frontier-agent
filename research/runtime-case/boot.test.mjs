import test from 'node:test';
import assert from 'node:assert/strict';
import { boot } from './boot.mjs';
function subject(path) {
 let ready;
 const auth = new Promise(resolve => { ready = resolve; });
 const state = { landing: undefined, publicLoads: 0, privateLoads: 0 };
 const finished = boot({path,state,initAuth:()=>auth,loadPublic:()=>state.publicLoads++,loadPrivate:()=>state.privateLoads++});
 return {state,ready,finished};
}
test('a deep link must not display the landing hero while auth is pending',async()=>{
 const s=subject('/runtime');try{assert.equal(s.state.landing,false);}finally{s.ready();await s.finished;}
});
test('offline public content renders before auth completes',async()=>{
 const s=subject('/runtime');try{assert.equal(s.state.publicLoads,1);}finally{s.ready();await s.finished;}assert.equal(s.state.publicLoads,1);
});
test('private content waits for identity and loads exactly once',async()=>{
 const s=subject('/experiments');assert.equal(s.state.privateLoads,0);s.ready();await s.finished;assert.equal(s.state.privateLoads,1);
});
test('the root route retains its landing page and loads no private view',async()=>{
 const s=subject('/');assert.equal(s.state.landing,true);s.ready();await s.finished;assert.equal(s.state.privateLoads,0);assert.equal(s.state.publicLoads,0);
});
