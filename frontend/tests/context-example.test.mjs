import test from 'node:test';
import assert from 'node:assert/strict';
import { contextExample } from '../src/context-example.js';
test('second request retains context and matches the result to the tool call', () => {
  const [first, call, execution, second] = contextExample();
  assert.deepEqual(second.messages.slice(0, 2), first.messages);
  assert.deepEqual(second.tools, first.tools);
  assert.deepEqual(second.messages[2], call);
  assert.equal(second.messages[3].tool_call_id, call.tool_calls[0].id);
  assert.deepEqual(JSON.parse(second.messages[3].content), execution.result);
  assert.deepEqual(JSON.parse(call.tool_calls[0].function.arguments), execution.arguments);
});
test('skill toggle changes instructions without inventing an API field', () => {
  const enabled = contextExample(), disabled = contextExample(false);
  assert.match(enabled[0].messages[0].content, /Loaded skill:/);
  assert.doesNotMatch(disabled[0].messages[0].content, /Loaded skill:/);
  assert.equal('skills' in enabled[0], false);
  assert.deepEqual(enabled[0].tools, disabled[0].tools);
  assert.match(disabled[4].content, /not loaded a skill/);
  enabled[0].messages[0].content = 'changed';
  assert.match(contextExample()[0].messages[0].content, /You are a learning assistant/);
});
