import test from 'node:test';
import assert from 'node:assert/strict';
import { clientRoute, ROUTE_VIEWS } from '../src/route-links.js';
test('same-language reading links preserve queries and use client routing',()=>{
 const current='https://example.org/feed?lang=zh';
 assert.equal(clientRoute('/feed?lang=zh&q=demo',current).searchParams.get('q'),'demo');
 assert.equal(clientRoute('/experiments?lang=zh',current).pathname,'/experiments');
 for(const href of ['/api/auth/me','/rss/digest.xml','/feed?lang=en','https://outside.org/feed?lang=zh','/feed?lang=zh#part'])assert.equal(clientRoute(href,current),null);
});
test('explicit links match the resolved language even without a lang query',()=>{
 assert.equal(clientRoute('/feed?lang=zh','https://example.org/feed','zh').pathname,'/feed');
 assert.equal(clientRoute('/feed?lang=en','https://example.org/feed','zh'),null);
});
test('retired learning modules are no longer client routes',()=>{
 for(const view of ['runtime','academy','context']){
  assert.ok(!ROUTE_VIEWS.includes(view));
  assert.equal(clientRoute('/'+view,'https://example.org/feed','zh'),null);
 }
});
