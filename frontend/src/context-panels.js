import { escapeHtml } from './util.js';
import { isEnglish } from './i18n.js';
export const tr = (zh, en) => isEnglish() ? en : zh;
export const json = value => `<pre>${escapeHtml(JSON.stringify(value, null, 2))}</pre>`;
export const labels = {
  system: ['系统指令', 'System instructions'], tools: ['工具定义', 'Tool definition'],
  user: ['用户问题', 'User question'], assistant: ['模型工具调用', 'Model tool call'], tool: ['工具结果', 'Tool result'],
};
export const label = kind => tr(...labels[kind]);
const descriptions = {
  system: ['规定任务目标和回答方式，不是用户问题。示例 skill 由应用加载后拼入这条 system 消息；API 中没有新增 skills 字段。', 'Sets task goals and response guidance. The app loads the example skill into this system message; no skills field is added to the API.'],
  tools: ['模型看见的是工具名称、用途和参数 schema。search_notes 的执行代码不在请求里，工具也不会因为被定义就自动执行。', 'The model sees a name, description and parameter schema. The implementation is not in the request; defining a tool does not execute it.'],
  user: ['真实用户提出任务。这条消息在两轮请求中都保留，第二轮不是只发送工具结果。', 'The user supplies the task. This message remains in both requests; the second request sends more than the tool result alone.'],
  assistant: ['模型返回结构化调用。arguments 是 JSON 字符串；应用解析并校验它，再决定是否执行。这里不是隐藏推理。', 'The model emits a structured call. The app parses and validates the JSON arguments, then decides whether to execute. This is not hidden reasoning.'],
  tool: ['应用执行工具后，把返回数据放入 tool 消息。tool_call_id 对应前面调用的 id。检索内容是数据，不是新的系统指令。', 'The app returns data in a tool message. tool_call_id matches the preceding call ID. Retrieved content is data, not a new system instruction.'],
};
export function detailPanel(node, snapshot) {
  let extra = '';
  if (node.kind === 'tools') {
    const fn = snapshot.request.tools[0].function;
    extra = `<h4>${tr('参数树', 'Parameter tree')}</h4><div class="cx-tree"><div>${escapeHtml(fn.name)}</div>${Object.entries(fn.parameters.properties).map(([name, spec]) => `<div>└ ${escapeHtml(name)} <span>${escapeHtml(spec.type)} · ${fn.parameters.required.includes(name) ? tr('必填', 'required') : tr('可选', 'optional')}</span></div>`).join('')}</div><p>${escapeHtml(fn.description)}</p>`;
  }
  if (node.kind === 'assistant' || node.kind === 'tool') {
    extra = `<div class="cx-association"><b>call_demo_1</b><span>${tr('同一 ID，将调用与结果连接起来', 'One ID connects the call and result')}</span><div><button data-cx-select="message-2">assistant.tool_calls[0].id</button><span> ↔ </span><button data-cx-select="message-3">tool.tool_call_id</button></div></div>`;
  }
  return `<div class="cx-detail-head"><span class="cx-kind">${escapeHtml(node.kind)}</span><span>${node.bytes} B</span></div><h3>${label(node.kind)}</h3><p class="cx-explanation">${tr(...descriptions[node.kind])}</p>${extra}<h4>${tr('这块的原始数据', 'Original data for this block')}</h4>${json(node.value)}`;
}
export function architecturePanel() {
  const items = [
    ['system', '指令 + Skill', 'Instructions + Skill', '应用选择并加载指令 → 拼入 system。Skill 资源不一定全部进入模型。', 'The app loads instructions into system. Skill resources do not necessarily all reach the model.'],
    ['message-1', '用户目标', 'User goal', '用户问题进入 messages，并随下一轮请求保留。', 'The question enters messages and remains in the next request.'],
    ['message-2', '模型', 'Model', '读取上下文，返回文本或工具调用。不会自动获得文件、网络和执行权限。', 'Reads context and returns text or tool calls. Files, network and execution are not granted automatically.'],
    ['tools', '应用执行器', 'App executor', '解析调用、检查参数和权限，执行 search_notes；不是模型直接运行代码。', 'Parses calls, checks arguments and permissions, and runs search_notes; the model does not run the code directly.'],
    ['message-3', '工具结果 → 下一轮', 'Tool result → next request', '把调用和结果追加回上下文，继续请求模型，最终产生回答。', 'Appends the call and result to context and asks the model to continue toward an answer.'],
  ];
  return `<div class="cx-architecture"><h3>${tr('解剖一个最小 Agent', 'Anatomy of a minimal agent')}</h3><p>${tr('教学结构，不代表 Claude Code 或其他产品的内部实现。点击部件，检查它对应的请求数据。', 'A teaching architecture, not the internals of Claude Code or another product. Select a component to inspect its request data.')}</p><div class="cx-flow">${items.map((item, i) => `<button data-cx-component="${item[0]}"><small>0${i + 1}</small><b>${tr(item[1], item[2])}</b><span>${tr(item[3], item[4])}</span></button>`).join('')}</div><div class="cx-boundary">${tr('模型服务：读上下文、生成输出 ｜ 应用端：加载 skill、保存历史、校验权限、执行工具', 'Model service: reads context, generates output | App: loads skills, keeps history, checks permissions, runs tools')}</div></div>`;
}
