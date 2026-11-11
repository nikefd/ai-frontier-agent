import { detectProtocol, requestItems, PROTOCOLS } from './request-adapters.js';
export const byteSize = value => new TextEncoder().encode(JSON.stringify(value) ?? '').length;
export function readJson(source) {
  if (new TextEncoder().encode(source).length > 1024 * 1024) throw new Error('Request limit: 1 MiB');
  const raw = JSON.parse(source);
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error('Expected a JSON object');
  return raw;
}
export function inspectRequest(source, selected = 'auto') {
  const raw = typeof source === 'string' ? readJson(source) : readJson(JSON.stringify(source));
  const protocol = selected === 'auto' ? detectProtocol(raw) : selected;
  if (!PROTOCOLS.includes(protocol)) throw new Error('Unsupported protocol');
  if ([raw.messages, raw.contents, raw.input].some(a => Array.isArray(a) && a.length > 200) || (raw.tools?.length || 0) > 100) throw new Error('Limit: 200 messages / 100 tools');
  if (raw.tools !== undefined && !Array.isArray(raw.tools)) throw new Error('tools must be an array');
  const normalized = requestItems(raw, protocol), warnings = [];
  if (selected === 'auto' && protocol === 'chat') warnings.push('Auto detection is heuristic; select Claude explicitly for ambiguous messages-only requests.');
  const items = normalized.items.map(item => ({ ...item, bytes: byteSize(item.value) }));
  if (items.length > 500) throw new Error('Too many context blocks (limit 500)');
  const links = normalized.calls.map(c => ({ ...c, matches: normalized.results.filter(r => r.order > c.order && (c.id ? r.id === c.id : protocol === 'gemini' && !r.id && r.name === c.name)) }));
  const ids = normalized.calls.filter(c => c.id).map(c => c.id);
  if (new Set(ids).size !== ids.length) warnings.push('Duplicate call IDs: association is ambiguous.');
  links.forEach(link => {
    if (!normalized.tools.some(t => t.name === link.name)) warnings.push(`Call ${link.name}: no matching definition in supplied tools (it may be server-managed).`);
    if (!link.id) warnings.push(protocol === 'gemini' ? 'Gemini call has no ID; association is by name, not proof of a unique match.' : 'Call ID is missing.');
    if (!link.matches.length) warnings.push(`No later result for ${link.id || link.name || 'unnamed call'} (may be a partial request).`);
    if (link.matches.length > 1) warnings.push('Multiple matching results: inspect the original ordering.');
    if (typeof link.args === 'string') try { JSON.parse(link.args); } catch { warnings.push('Tool arguments are not valid JSON.'); }
  });
  if (normalized.results.some(r => !links.some(l => l.matches.includes(r)))) warnings.push('Result without a preceding matching call.');
  if (raw.previous_response_id || raw.conversation) warnings.push('Server-side conversation state is referenced; this input does not contain the complete context.');
  const groups = ['system', 'tools', 'message', 'result', 'controls'].map(kind => ({ kind, bytes: items.filter(i => i.kind === kind).reduce((n, i) => n + i.bytes, 0) }));
  return { raw, protocol, items, tools: normalized.tools, links, results: normalized.results, warnings: [...new Set(warnings)], groups, bytes: byteSize(raw), blockBytes: groups.reduce((n, g) => n + g.bytes, 0) };
}
export function compareRequests(left, right) {
  const before = new Map(left.items.map(i => [i.path, i]));
  const after = new Map(right.items.map(i => [i.path, i]));
  return [...new Set([...before.keys(), ...after.keys()])].map(path => ({ path, before: before.get(path), after: after.get(path), change: !before.has(path) ? 'added' : !after.has(path) ? 'removed' : JSON.stringify(before.get(path).value) === JSON.stringify(after.get(path).value) ? 'unchanged' : 'changed' }));
}
export function stripInstructions(raw, protocol, stripTools = false) {
  const copy = JSON.parse(JSON.stringify(raw));
  delete copy.system; delete copy.instructions; delete copy.systemInstruction;
  if (Array.isArray(copy.messages)) copy.messages = copy.messages.filter(m => !['system', 'developer'].includes(m.role));
  if (Array.isArray(copy.input)) copy.input = copy.input.filter(m => !['system', 'developer'].includes(m.role));
  if (stripTools) delete copy.tools;
  return copy;
}
export function parameterRows(schema, path = '', depth = 0) {
  if (!schema || typeof schema !== 'object' || depth > 6) return [];
  const properties = schema.properties && typeof schema.properties === 'object' ? schema.properties : {};
  return Object.entries(properties).slice(0, 100).flatMap(([name, spec]) => {
    if (!spec || typeof spec !== 'object') return [{ path: path + name, type: 'unknown', required: false, depth }];
    return [{ path: path + name, type: Array.isArray(spec.type) && spec.type.every(t => typeof t === 'string') ? spec.type.join('|') : typeof spec.type === 'string' ? spec.type : 'unknown', required: Array.isArray(schema.required) && schema.required.includes(name), depth }, ...parameterRows(spec.type === 'array' ? spec.items : spec, path + name + (spec.type === 'array' ? '[].' : '.'), depth + 1)];
  });
}
