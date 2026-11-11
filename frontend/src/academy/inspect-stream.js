const LIMIT = 2 * 1024 * 1024;
export function streamEvents(source) {
  if (new TextEncoder().encode(source).length > LIMIT) throw new Error('Stream limit: 2 MiB');
  const trimmed = source.trim();
  if (trimmed.startsWith('[')) {
    const chunks = JSON.parse(trimmed);
    if (!Array.isArray(chunks) || chunks.length > 5000) throw new Error('Limit: 5000 events');
    return chunks.map((data, index) => ({ index, event: 'json-chunk', raw: JSON.stringify(data), data }));
  }
  const frames = source.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split(/\n\n+/).filter(s => s.trim() && s.split('\n').some(line => line.startsWith('data:')));
  if (frames.length > 5000) throw new Error('Limit: 5000 events');
  return frames.map((raw, index) => {
    const lines = raw.split('\n'), event = lines.find(l => l.startsWith('event:'))?.slice(6).trim() || 'message';
    const dataText = lines.filter(l => l.startsWith('data:')).map(l => l.slice(5).replace(/^ /, '')).join('\n');
    if (dataText === '[DONE]') return { index, event, raw, done: true };
    try { return { index, event, raw, data: JSON.parse(dataText) }; }
    catch { return { index, event, raw, error: 'Malformed or incomplete event JSON' }; }
  });
}
export function inspectStream(source, selected = 'auto') {
  const events = streamEvents(source), first = events.find(e => e.data)?.data;
  const protocol = selected !== 'auto' ? selected : first?.choices ? 'chat' : first?.candidates ? 'gemini' : String(first?.type || '').startsWith('response.') ? 'responses' : ['message_start','content_block_start','content_block_delta','ping','message_delta'].includes(first?.type) ? 'claude' : null;
  if (!['chat','claude','responses','gemini'].includes(protocol)) throw new Error('Cannot identify stream protocol; choose it explicitly.');
  const outputs = new Map(), tools = new Map(), responseItemKeys = new Map(), usage = {}, finish = [], errors = [], warnings = [];
  let stopped = false;
  const output = (id, delta) => outputs.set(id, (outputs.get(id) || '') + (typeof delta === 'string' ? delta : ''));
  const getTool = key => { if (!tools.has(key)) tools.set(key, { key, id: '', name: '', arguments: '' }); return tools.get(key); };
  for (const e of events) {
    if (e.error) { warnings.push(`Event ${e.index}: ${e.error}`); continue; }
    if (e.done) { if (protocol === 'chat') stopped = finish.length > 0; continue; }
    const d = e.data;
    if (!d || typeof d !== 'object') { warnings.push(`Event ${e.index}: unsupported data`); continue; }
    if (d.error || d.type === 'error' || d.type === 'response.failed') { errors.push(d.error || d.response?.error || d); continue; }
    let recognized = false;
    if (protocol === 'chat' && Array.isArray(d.choices)) {
      recognized = true;
      d.choices.forEach(c => {
        const key = String(c.index ?? 0), delta = c.delta || {};
        output(key, delta.content);
        (delta.tool_calls || []).forEach(call => {
          const tool = getTool(key + ':' + (call.index ?? 0));
          if (call.id) tool.id = call.id;
          if (call.function?.name) tool.name += call.function.name;
          if (call.function?.arguments) tool.arguments += call.function.arguments;
        });
        if (c.finish_reason) { finish.push({ channel: key, reason: c.finish_reason }); stopped = true; }
      });
      if (d.usage) Object.assign(usage, d.usage);
    } else if (protocol === 'claude') {
      const type = d.type || e.event, key = String(d.index ?? 0);
      recognized = ['message_start','message_delta','message_stop','content_block_start','content_block_delta','content_block_stop','ping'].includes(type);
      if (type === 'message_start' && d.message?.usage) Object.assign(usage, d.message.usage);
      if (type === 'content_block_start') {
        if (d.content_block?.type === 'tool_use') Object.assign(getTool(key), { id: d.content_block.id, name: d.content_block.name, initial: d.content_block.input });
        if (d.content_block?.type === 'text') output(key, d.content_block.text);
      }
      if (type === 'content_block_delta') {
        if (d.delta?.type === 'text_delta') output(key, d.delta.text);
        if (d.delta?.type === 'input_json_delta') getTool(key).arguments += d.delta.partial_json || '';
        // Thinking/signature deltas remain raw events, never decoded or inferred.
      }
      if (type === 'message_delta') { if (d.usage) Object.assign(usage, d.usage); if (d.delta?.stop_reason) finish.push({ reason: d.delta.stop_reason }); }
      if (type === 'message_stop') stopped = true;
    } else if (protocol === 'responses') {
      const type = d.type || e.event;
      const key = d.output_index !== undefined ? String(d.output_index) : responseItemKeys.get(d.item_id) ?? String(d.item_id ?? 0);
      if (d.item?.id) responseItemKeys.set(d.item.id, key);
      recognized = type.startsWith('response.');
      if (type === 'response.output_text.delta') output(key + ':' + (d.content_index ?? 0), d.delta);
      if (type === 'response.output_text.done') outputs.set(key + ':' + (d.content_index ?? 0), d.text || '');
      if (type === 'response.output_item.added' && d.item?.type === 'function_call') Object.assign(getTool(key), { id: d.item.call_id, name: d.item.name, arguments: d.item.arguments || '' });
      if (type === 'response.function_call_arguments.delta') getTool(key).arguments += d.delta || '';
      if (type === 'response.function_call_arguments.done') { const t = getTool(key); t.arguments = d.arguments || t.arguments; if (d.name) t.name = d.name; }
      if (type === 'response.completed' || type === 'response.incomplete') {
        stopped = type === 'response.completed'; finish.push({ reason: d.response?.status || (stopped ? 'completed' : 'incomplete') });
        if (d.response?.usage) Object.assign(usage, d.response.usage);
        (d.response?.output || []).forEach((item, i) => {
          if (item.type === 'function_call') Object.assign(getTool(String(i)), { id: item.call_id, name: item.name, arguments: item.arguments });
          if (item.type === 'message') (item.content || []).forEach((p, j) => { if (p.type === 'output_text') outputs.set(i + ':' + j, p.text || ''); });
        });
      }
    } else if (protocol === 'gemini' && Array.isArray(d.candidates)) {
      recognized = true;
      d.candidates.forEach((candidate, i) => {
        const key = String(candidate.index ?? i);
        (candidate.content?.parts || []).forEach((p, j) => {
          if (p.text && !p.thought) output(key, p.text);
          if (p.functionCall?.partialArgs) warnings.push('Gemini partialArgs extension retained in raw view; not reconstructed.');
          if (p.functionCall) Object.assign(getTool(key + ':' + j), { id: p.functionCall.id || '', name: p.functionCall.name, arguments: JSON.stringify(p.functionCall.args || {}) });
        });
        if (candidate.finishReason) { stopped = true; finish.push({ channel: key, reason: candidate.finishReason }); }
      });
      if (d.usageMetadata) Object.assign(usage, d.usageMetadata);
    }
    if (!recognized) warnings.push(`Event ${e.index}: unknown event preserved in raw view`);
  }
  const calls = [...tools.values()].map(t => {
    if (typeof t.id !== 'string') t.id = '';
    if (typeof t.name !== 'string') t.name = 'unknown';
    if (typeof t.arguments !== 'string') t.arguments = JSON.stringify(t.arguments ?? {});
    let args; try { args = JSON.parse(t.arguments || JSON.stringify(t.initial || {})); } catch { warnings.push(`Incomplete tool JSON: ${t.id || t.key}`); }
    return { ...t, parsedArguments: args };
  });
  if (!stopped) warnings.push('No complete stop marker observed; the stream may be interrupted.');
  return { protocol, events, outputs: [...outputs].map(([channel, text]) => ({ channel, text })), calls, usage, finish, errors, warnings, complete: stopped && !errors.length && !events.some(e => e.error) && !warnings.some(w => w.startsWith('Incomplete tool JSON')) };
}
