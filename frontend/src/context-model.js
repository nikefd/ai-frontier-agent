import { contextExample } from './context-example.js';
export const bytes = value => new TextEncoder().encode(JSON.stringify(value)).length;
export function lessonSnapshot(round = 0, skill = true) {
  const example = contextExample(skill);
  const request = example[round === 1 ? 3 : 0];
  const nodes = request.messages.map((message, index) => ({ key: 'message-' + index, kind: message.role, value: message, bytes: bytes(message), added: index >= 2 }));
  nodes.splice(1, 0, { key: 'tools', kind: 'tools', value: request.tools, bytes: bytes(request.tools), added: false });
  return { request, nodes, total: nodes.reduce((n, node) => n + node.bytes, 0), requestBytes: bytes(request), call: example[1], result: example[3].messages[3], answer: example[4], skill };
}
export function lessonDifference(skill = true) {
  const before = lessonSnapshot(0, skill), after = lessonSnapshot(1, skill);
  return { before, after, added: after.nodes.filter(node => node.added), delta: after.requestBytes - before.requestBytes };
}
