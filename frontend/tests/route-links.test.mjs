import test from 'node:test';
import assert from 'node:assert/strict';
import {clientRoute} from '../src/route-links.js';
test('learning links with the same language use client routing, preserving queries',()=>{
 const current='https://example.org/academy?lang=zh';
 assert.equal(clientRoute('/academy?lang=zh&model=demo',current).searchParams.get('model'),'demo');
 assert.equal(clientRoute('/context?lang=zh&case=recovery&step=2',current).pathname,'/context');
 for(const href of ['/api/auth/me','/rss/digest.xml','/academy?lang=en','https://outside.org/academy?lang=zh','/academy?lang=zh#part'])assert.equal(clientRoute(href,current),null);
});
test('explicit links matching the resolved language also stay in a document without lang query',()=>{
 assert.equal(clientRoute('/academy?lang=zh&tab=agents','https://example.org/academy','zh').pathname,'/academy');
 assert.equal(clientRoute('/academy?lang=en','https://example.org/academy','zh'),null);
});
