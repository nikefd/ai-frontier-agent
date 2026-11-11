import { contextExample } from '../context-example.js';
export const protocolNames = { chat: 'Chat Completions', claude: 'Claude Messages', responses: 'OpenAI Responses', gemini: 'Gemini GenerateContent' };
export const protocolDocs = {
  chat: 'https://developers.openai.com/api/docs/guides/function-calling',
  responses: 'https://developers.openai.com/api/docs/guides/function-calling',
  claude: 'https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview',
  gemini: 'https://aistudio.google.com/docs/function-calling',
};
export function protocolExample(protocol, second = true) {
  const example = contextExample(), chat = example[second ? 3 : 0], [system, user] = chat.messages;
  const tool = chat.tools[0].function, call = example[1].tool_calls[0], result = example[3].messages[3];
  if (protocol === 'chat') return chat;
  if (protocol === 'claude') return { model: '<claude-model>', max_tokens: 1024, system: [{ type: 'text', text: system.content, cache_control: { type: 'ephemeral' } }], tools: [{ name: tool.name, description: tool.description, input_schema: tool.parameters }], messages: [{ role: 'user', content: user.content }, ...(second ? [{ role: 'assistant', content: [{ type: 'tool_use', id: call.id, name: tool.name, input: JSON.parse(call.function.arguments) }] }, { role: 'user', content: [{ type: 'tool_result', tool_use_id: call.id, content: result.content }] }] : [])] };
  if (protocol === 'responses') return { model: '<responses-model>', instructions: system.content, tools: [{ type: 'function', ...tool }], input: [{ role: 'user', content: user.content }, ...(second ? [{ type: 'function_call', call_id: call.id, name: tool.name, arguments: call.function.arguments }, { type: 'function_call_output', call_id: call.id, output: result.content }] : [])] };
  if (protocol === 'gemini') return { systemInstruction: { parts: [{ text: system.content }] }, tools: [{ functionDeclarations: [{ name: tool.name, description: tool.description, parameters: tool.parameters }] }], contents: [{ role: 'user', parts: [{ text: user.content }] }, ...(second ? [{ role: 'model', parts: [{ functionCall: { id: call.id, name: tool.name, args: JSON.parse(call.function.arguments) } }] }, { role: 'user', parts: [{ functionResponse: { id: call.id, name: tool.name, response: JSON.parse(result.content) } }] }] : [])] };
  throw new Error('Unknown protocol');
}
export function streamExample(protocol) {
  const frame = (data, event) => (event ? `event: ${event}\n` : '') + 'data: ' + JSON.stringify(data) + '\n\n';
  if (protocol === 'chat') return frame({ choices: [{ index: 0, delta: { content: 'A tool ' } }] }) + frame({ choices: [{ index: 0, delta: { content: 'executes an operation.' }, finish_reason: 'stop' }], usage: { prompt_tokens: 100, completion_tokens: 8, total_tokens: 108 } }) + 'data: [DONE]\n\n';
  if (protocol === 'claude') return [
    { type: 'message_start', message: { usage: { input_tokens: 100, output_tokens: 0, cache_read_input_tokens: 50 } } },
    { type: 'content_block_start', index: 0, content_block: { type: 'tool_use', id: 'call_demo_1', name: 'search_notes', input: {} } },
    { type: 'content_block_delta', index: 0, delta: { type: 'input_json_delta', partial_json: '{"query":' } },
    { type: 'content_block_delta', index: 0, delta: { type: 'input_json_delta', partial_json: '"tools"}' } },
    { type: 'content_block_stop', index: 0 }, { type: 'message_delta', delta: { stop_reason: 'tool_use' }, usage: { output_tokens: 18 } }, { type: 'message_stop' },
  ].map(d => frame(d, d.type)).join('');
  if (protocol === 'responses') return [{ type: 'response.created', response: { status: 'in_progress' } }, { type: 'response.output_text.delta', output_index: 0, content_index: 0, delta: 'A tool executes an operation.' }, { type: 'response.completed', response: { status: 'completed', usage: { input_tokens: 100, output_tokens: 8, total_tokens: 108 } } }].map(d => frame(d, d.type)).join('');
  if (protocol === 'gemini') return [{ candidates: [{ index: 0, content: { role: 'model', parts: [{ text: 'A tool ' }] } }] }, { candidates: [{ index: 0, content: { role: 'model', parts: [{ text: 'executes an operation.' }] }, finishReason: 'STOP' }], usageMetadata: { promptTokenCount: 100, candidatesTokenCount: 8, totalTokenCount: 108 } }].map(d => frame(d)).join('');
}
