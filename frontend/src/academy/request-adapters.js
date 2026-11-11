// Provider-specific wire shapes are normalized without executing imported content.
const string = (value, fallback = '') => typeof value === 'string' ? value : fallback;
const list = value => Array.isArray(value) ? value : [];
export const PROTOCOLS = ['chat', 'claude', 'responses', 'gemini'];
export function detectProtocol(raw) {
  if ('contents' in raw) return 'gemini';
  if ('input' in raw || 'previous_response_id' in raw) return 'responses';
  if ('messages' in raw && ('anthropic_version' in raw || 'system' in raw || 'max_tokens' in raw && list(raw.tools).some(t => t?.input_schema))) return 'claude';
  if ('messages' in raw) return 'chat';
  throw new Error('Unrecognized request shape. Select a supported protocol.');
}
export function requestItems(raw, protocol) {
  const items = [], calls = [], results = [], tools = [];
  const add = (path, kind, value, role = kind, blocks = []) => {
    const item = { key: path, path, kind, role, value, blocks, index: items.length };
    items.push(item); return item;
  };
  const call = (item, id, name, args) => calls.push({ item: item.key, order: item.index, id: string(id), name: string(name, 'unknown'), args });
  const result = (item, id, name, value, error = false) => results.push({ item: item.key, order: item.index, id: string(id), name: string(name), value, error });
  const tool = (path, value, fn) => { add(path, 'tools', value); tools.push({ path, name: string(fn?.name, string(value?.type, 'unknown')), description: string(fn?.description), schema: fn?.parameters || fn?.input_schema || {}, raw: value }); };
  const covered = new Set(['model', 'stream']);
  if (protocol === 'chat' || protocol === 'claude') {
    if (!Array.isArray(raw.messages)) throw new Error('messages must be an array');
    covered.add('messages'); covered.add('tools');
    if (raw.system !== undefined) { add('system', 'system', raw.system); covered.add('system'); }
    raw.messages.forEach((message, i) => {
      if (!message || typeof message !== 'object' || Array.isArray(message)) throw new Error('Each message must be an object');
      const blocks = list(message.content);
      const kind = ['system', 'developer'].includes(message.role) ? 'system' : message.role === 'tool' || blocks.length && blocks.every(b => b?.type === 'tool_result') ? 'result' : 'message';
      const item = add(`messages[${i}]`, kind, message, string(message.role, 'unknown'), blocks);
      for (const c of list(message.tool_calls)) call(item, c?.id, c?.function?.name, c?.function?.arguments);
      if (message.role === 'tool') result(item, message.tool_call_id, null, message.content);
      blocks.forEach(block => {
        if (block?.type === 'tool_use' || block?.type === 'server_tool_use') call(item, block.id, block.name, block.input);
        if (block?.type === 'tool_result') result(item, block.tool_use_id, null, block.content, block.is_error === true);
      });
    });
    list(raw.tools).forEach((t, i) => tool(`tools[${i}]`, t, t?.function || t));
  } else if (protocol === 'responses') {
    covered.add('instructions'); covered.add('input'); covered.add('tools');
    if (raw.instructions !== undefined) add('instructions', 'system', raw.instructions);
    if (typeof raw.input === 'string') add('input', 'message', raw.input, 'user');
    const input = list(raw.input);
    if (raw.input !== undefined && typeof raw.input !== 'string' && !Array.isArray(raw.input)) throw new Error('input must be a string or array');
    input.forEach((value, i) => {
      if (!value || typeof value !== 'object') throw new Error('Each input item must be an object');
      const item = add(`input[${i}]`, ['system', 'developer'].includes(value.role) ? 'system' : value.type === 'function_call_output' ? 'result' : 'message', value, string(value.role, string(value.type, 'unknown')), list(value.content));
      if (value.type === 'function_call') call(item, value.call_id, value.name, value.arguments);
      if (value.type === 'function_call_output') result(item, value.call_id, null, value.output);
    });
    list(raw.tools).forEach((t, i) => tool(`tools[${i}]`, t, t));
  } else if (protocol === 'gemini') {
    if (!Array.isArray(raw.contents)) throw new Error('contents must be an array');
    covered.add('contents'); covered.add('tools'); covered.add('systemInstruction');
    if (raw.systemInstruction !== undefined) add('systemInstruction', 'system', raw.systemInstruction);
    raw.contents.forEach((value, i) => {
      if (!value || typeof value !== 'object' || !Array.isArray(value.parts)) throw new Error('Each content must have parts[]');
      const item = add(`contents[${i}]`, value.parts.length && value.parts.every(p => p?.functionResponse) ? 'result' : 'message', value, string(value.role, 'user'), value.parts);
      value.parts.forEach(part => {
        if (part?.functionCall) { const c = part.functionCall; call(item, c.id, c.name, c.args); }
        if (part?.functionResponse) { const r = part.functionResponse; result(item, r.id, r.name, r.response); }
      });
    });
    list(raw.tools).forEach((t, i) => {
      if (Array.isArray(t?.functionDeclarations)) {
        t.functionDeclarations.forEach((fn, j) => tool(`tools[${i}].functionDeclarations[${j}]`, fn, fn));
        for (const [key, value] of Object.entries(t)) if (key !== 'functionDeclarations') add(`tools[${i}].${key}`, 'tools', value);
      }
      else tool(`tools[${i}]`, t, t);
    });
  } else throw new Error('Unsupported protocol');
  for (const [key, value] of Object.entries(raw)) if (!covered.has(key)) add(key, 'controls', value);
  return { items, calls, results, tools };
}
