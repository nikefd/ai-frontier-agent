import { isEnglish } from './i18n.js';
import { escapeHtml } from './util.js';
import { contextExample } from './context-example.js';
import './context-lab.css';
const text = (zh, en) => isEnglish() ? en : zh;
const steps = [
  ['请求 1：组装上下文', 'Request 1: build context', '应用把 system、用户问题和工具定义发送给模型。工具的实现代码没有发过去。', 'The app sends instructions, the user question and a tool schema. The tool implementation stays in the app.'],
  ['模型：请求调用工具', 'Model: request a tool', '模型输出工具名称与 JSON 参数；这还不是执行结果，也不是隐藏思维过程。', 'The model returns a tool name and JSON arguments. This is neither an execution result nor hidden reasoning.'],
  ['应用：执行工具', 'App: execute the tool', '应用校验参数和权限，再执行工具。本例读取虚构笔记，不访问网络或本机文件。', 'The app validates arguments and permissions, then runs the tool. This fixture uses fictional notes, without network or filesystem access.'],
  ['请求 2：加入工具结果', 'Request 2: include the result', '保留原始上下文和 assistant 工具调用，再加入 tool 消息。tool_call_id 必须对应调用 ID。', 'Keep the original context and assistant tool call, then append the tool message. tool_call_id matches the call ID.'],
  ['模型：最终回答', 'Model: final answer', '模型根据收到的结果回答。实际 Agent 可能继续调用工具、处理错误或停止；这里仅展示一次成功循环。', 'The model answers using the returned result. Real agents may continue, handle errors or stop; this shows one successful loop.'],
];
let step = 0, withSkill = true;
export function loadContextLab() {
  const root = document.querySelector('#context-lab');
  const example = contextExample(withSkill), data = example[step];
  const title = item => item[isEnglish() ? 1 : 0];
  root.innerHTML = `<div class="card context-lab">
    <h2>${text('一次请求里，模型究竟看到了什么？', 'What does the model receive in a request?')}</h2>
    <p class="muted-card">${text('离线教学演示 · 无 API 费用 · 所有回答与笔记均为预先编写，非真实运行记录。', 'Offline teaching demo · No API cost · Answers and notes are authored fixtures, not a real execution trace.')}</p>
    <p>${text('场景：学习助手查课程笔记，解释 tool 与 skill 的区别。', 'Scenario: a learning assistant searches course notes to explain tools and skills.')}</p>
    <label><input id="context-skill" type="checkbox" ${withSkill ? 'checked' : ''}> ${text('加载 explain-with-evidence skill，比较 system 的变化', 'Load the explain-with-evidence skill and compare the system message')}</label>
    <p class="text-faint">${text('本例由应用把 skill 指令并入 system；skill 不是这里的 API 字段。实际框架也可能用其他消息或按需加载文件。开关只改变示例输入，不预测模型输出。', 'This app inserts skill instructions into system; skill is not an API field here. Frameworks may use other messages or load files on demand. The switch changes the fixture input, not a prediction of model output.')}</p>
    <ol class="context-steps" aria-label="${text('执行步骤', 'Execution steps')}">${steps.map((item, i) => `<li><button data-context-step="${i}" ${i === step ? 'aria-current="step"' : ''}>${i + 1}. ${title(item)}</button></li>`).join('')}</ol>
    <section aria-live="polite" aria-atomic="true"><h3>${title(steps[step])}</h3><p>${steps[step][isEnglish() ? 3 : 2]}</p></section>
    ${data.messages ? `<div class="context-blocks">${data.messages.map((message, i) => `<details ${i === data.messages.length - 1 ? 'open' : ''}><summary>${i + 1}. ${escapeHtml(message.role)}${i > 1 ? ' · ' + text('本轮新增', 'added this round') : ''}</summary><pre>${escapeHtml(JSON.stringify(message, null, 2))}</pre></details>`).join('')}<details><summary>tools · ${text('工具接口，不是实现', 'interface, not implementation')}</summary><pre>${escapeHtml(JSON.stringify(data.tools, null, 2))}</pre></details></div>` : ''}
    <details class="context-payload" open><summary>${data.messages ? text('完整请求 JSON', 'Full request JSON') : text('本步数据 JSON', 'Step data JSON')}</summary><pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre></details>
    <div class="context-actions"><button id="context-prev" ${step === 0 ? 'disabled' : ''}>← ${text('上一步', 'Previous')}</button><span>${step + 1} / ${steps.length}</span><button id="context-next" ${step === steps.length - 1 ? 'disabled' : ''}>${text('下一步', 'Next')} →</button><button id="context-reset">${text('重新开始', 'Restart')}</button></div>
    <p class="text-faint">${text('格式：Chat Completions 风格；model 为占位符，JSON 为节选，不可直接运行，也不代表所有模型或闭源 Agent 的内部结构。', 'Format: Chat Completions style. The model is a placeholder and JSON is excerpted, not directly executable or a representation of every model or closed-source agent.')}</p>
    <a href="https://developers.openai.com/api/docs/guides/function-calling" target="_blank" rel="noopener noreferrer">${text('参考：OpenAI 官方工具调用文档', 'Reference: official OpenAI function calling documentation')} ↗</a>
  </div>`;
  root.querySelectorAll('[data-context-step]').forEach(button => button.addEventListener('click', () => { step = Number(button.dataset.contextStep); loadContextLab(); }));
  root.querySelector('#context-prev').onclick = () => { step = Math.max(0, step - 1); loadContextLab(); };
  root.querySelector('#context-next').onclick = () => { step = Math.min(steps.length - 1, step + 1); loadContextLab(); };
  root.querySelector('#context-reset').onclick = () => { step = 0; withSkill = true; loadContextLab(); };
  root.querySelector('#context-skill').onchange = event => { withSkill = event.target.checked; step = 0; loadContextLab(); };
}
