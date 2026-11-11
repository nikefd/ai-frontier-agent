import test from 'node:test';
import assert from 'node:assert/strict';
import { bytes, lessonSnapshot, lessonDifference } from '../src/context-model.js';
test('composition counts UTF-8 compact JSON bytes, not characters or tokens', () => {
  assert.equal(bytes('中文'), 8);
  const snapshot = lessonSnapshot(1);
  assert.equal(snapshot.total, snapshot.nodes.reduce((sum, node) => sum + bytes(node.value), 0));
  assert.equal(snapshot.requestBytes, bytes(snapshot.request));
  assert.ok(snapshot.requestBytes > snapshot.total);
});
test('comparison adds a matched call and result while keeping original context', () => {
  const diff = lessonDifference();
  assert.deepEqual(diff.added.map(n => n.kind), ['assistant', 'tool']);
  for (const node of diff.before.nodes) assert.deepEqual(diff.after.nodes.find(n => n.key === node.key).value, node.value);
  assert.equal(diff.after.call.tool_calls[0].id, diff.after.result.tool_call_id);
  assert.equal(diff.delta, bytes(diff.after.request) - bytes(diff.before.request));
});
test('skill toggle only changes system input and reduces request bytes', () => {
  const enabled = lessonSnapshot(1), disabled = lessonSnapshot(1, false);
  assert.ok(enabled.requestBytes > disabled.requestBytes);
  assert.deepEqual(enabled.nodes.slice(1), disabled.nodes.slice(1));
  assert.doesNotMatch(disabled.request.messages[0].content, /Loaded skill/);
});
