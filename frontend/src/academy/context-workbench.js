import { models } from './catalog.js';
import { exampleForModel } from './model-views.js';
import { escapeHtml as esc } from '../util.js';
import { loadContextLab } from '../context-lab.js';
import { tr } from '../context-panels.js';
import { inspectRequest, compareRequests, stripInstructions } from './inspect-request.js';
import { inspectStream } from './inspect-stream.js';
import { associateStream } from './stream-association.js';
import { protocolExample, streamExample, protocolNames, protocolDocs } from './protocol-examples.js';
import { requestOverview, streamPanel, pretty } from './inspect-panels.js';
import { lessons, lessonTrace } from './lessons.js';
import './academy.css';
let lastDataMode = 'request';
let mode = 'request', protocol = 'chat', source = '', other = '', report = null, index = 0, error = '', previousLink = '';
function loadExample() {
  source = mode === 'stream' ? streamExample(protocol === 'auto' ? 'chat' : protocol) : JSON.stringify(protocolExample(protocol === 'auto' ? 'chat' : protocol), null, 2);
  other = JSON.stringify(protocolExample(protocol === 'auto' ? 'chat' : protocol, false), null, 2);
  parse();
}
function parse() {
  try { report = mode === 'stream' ? inspectStream(source, protocol) : inspectRequest(source, protocol); index = 0; error = ''; }
  catch (e) { report = null; error = e.message; }
}
function comparison() {
  try {
    const rows = compareRequests(inspectRequest(other, protocol), report);
    return `<h3>${tr('基准请求 → 当前请求', 'Baseline → current request')}</h3><p>${tr('按字段路径比较；插入消息可能造成后续索引变化，不是语义匹配。', 'Compared by field path; message insertion can shift indices. This is not semantic alignment.')}</p><div class="ax-diff">${rows.map(r => `<details><summary><b>${r.change}</b> ${esc(r.path)}</summary><div class="ax-two">${pretty(r.before?.value ?? null)}${pretty(r.after?.value ?? null)}</div></details>`).join('')}</div>`;
  } catch (e) { return `<p role="alert">${esc(e.message)}</p>`; }
}
export function loadContextWorkbench() {
  const container = document.querySelector('#view-context');
  const params = new URLSearchParams(location.search), link = [params.get('protocol'), params.get('case'), params.get('step'), params.get('model')].join(':');
  if (link !== previousLink) {
    const requested = params.get('protocol');
    if (protocolNames[requested]) { protocol = requested; mode = 'request'; source = ''; report = null; error = ''; }
    const model = models.find(m => m.id === params.get('model'));
    if (model?.protocol) { protocol = model.protocol; mode = 'request'; source = JSON.stringify(exampleForModel(model), null, 2); other = JSON.stringify(exampleForModel(model, false), null, 2); parse(); }
    const lesson = lessons.find(l => l.id === params.get('case'));
    if (lesson) {
      const trace = lessonTrace(lesson.id), step = Math.max(0, Math.min(trace.length - 1, Number(params.get('step')) || 0));
      protocol = lesson.protocol; mode = 'request'; source = JSON.stringify(trace[step], null, 2); other = JSON.stringify(trace[Math.max(0, step - 1)], null, 2); parse();
    }
    previousLink = link;
  }
  if (!source && !report && !error) loadExample();
  container.innerHTML = `<div class="cx-app ax-workbench"><header class="cx-header"><div><span class="cx-eyebrow">AI FRONTIER / CONTEXT</span><h2>${tr('上下文解剖台', 'Context inspector')}</h2><p>${tr('导入、定位、对照：看清一次请求和流式输出。', 'Import, inspect and compare requests and streaming output.')}</p></div><a href="/academy?lang=${document.documentElement.lang === 'en' ? 'en' : 'zh'}">${tr('模型与 Agent 学习库 ↗', 'Model & agent academy ↗')}</a></header><nav class="cx-tabs" aria-label="${tr('解剖模式', 'Inspector modes')}">${[['request','请求解析','Request'],['stream','流式输出','Stream'],['lesson','引导学习','Guided lesson']].map(([key, zh, en]) => `<button data-ax-mode="${key}" aria-pressed="${mode === key}">${tr(zh,en)}</button>`).join('')}</nav><p class="cx-note">${tr('本地解析，不上传、不执行、不自动保存原始输入。支持常见字段；未知结构保留在原始视图。', 'Local parsing: inputs are not uploaded, executed or automatically saved. Common fields are supported; unknown structures remain in the raw view.')}</p><div id="ax-content"></div></div>`;
  const body = container.querySelector('#ax-content');
  if (mode === 'lesson') { body.innerHTML = '<div id="context-lab"></div>'; loadContextLab(); }
  else {
    body.innerHTML = `<div class="ax-editor"><div class="ax-toolbar"><label>${tr('协议', 'Protocol')} <select id="ax-protocol"><option value="auto">${tr('自动识别', 'Auto detect')}</option>${Object.entries(protocolNames).map(([key,name]) => `<option value="${key}">${name}</option>`).join('')}</select></label><button id="ax-example">${tr('载入教学示例', 'Load teaching example')}</button><label class="ax-file">${tr('导入文件', 'Import file')}<input type="file" id="ax-file" accept=".json,.txt,.sse,text/plain,application/json"></label><button id="ax-clear">${tr('清空私有输入', 'Clear private input')}</button></div><label for="ax-source">${mode === 'stream' ? 'SSE / JSON chunks' : tr('当前请求 JSON', 'Current request JSON')}</label><textarea id="ax-source" spellcheck="false" rows="10">${esc(source)}</textarea><div class="ax-toolbar"><button class="primary" id="ax-parse">${tr('解析并检查', 'Parse and inspect')}</button>${mode === 'request' ? `<button id="ax-omit-system">${tr('在副本中移除指令', 'Remove instructions in a copy')}</button><button id="ax-omit-tools">${tr('在副本中移除工具', 'Remove tools in a copy')}</button>` : ''}<a href="${protocolDocs[protocol] || protocolDocs.chat}" target="_blank" rel="noopener noreferrer">${tr('官方格式文档 ↗', 'Official format docs ↗')}</a></div></div><p role="alert" class="ax-error">${esc(error)}</p><div id="ax-report"></div>`;
    body.querySelector('#ax-protocol').value = protocol;
    const capture = () => { source = body.querySelector('#ax-source').value; const second = body.querySelector('#ax-other'); if (second) other = second.value; };
    const refreshReport = () => {
      const result = body.querySelector('#ax-report');
      result.innerHTML = !report ? '' : mode === 'stream' ? streamPanel(report) + `<details><summary>${tr('关联原始请求（可选）', 'Associate a supplied request (optional)')}</summary><p>${tr('仅按名称定位定义、按 ID 查找已提供的结果；不会执行工具。', 'Find definitions by name and supplied results by ID. Tools are not executed.')}</p><textarea id="ax-stream-request" rows="5" aria-label="Original request JSON">${esc(other)}</textarea><button id="ax-associate">${tr('检查关联', 'Check associations')}</button><div id="ax-associated"></div></details>` : `<div class="ax-metrics"><b>${esc(protocolNames[report.protocol])}</b><span>${report.items.length} ${tr('块', 'blocks')}</span><span>${report.links.length} ${tr('调用', 'calls')}</span></div><div id="ax-inspection">${requestOverview(report, index)}</div><details><summary>${tr('任意两份请求比较', 'Compare two requests')}</summary><label for="ax-other">${tr('基准 JSON（左侧）', 'Baseline JSON (left)')}</label><textarea id="ax-other" spellcheck="false" rows="6">${esc(other)}</textarea><button id="ax-compare">${tr('比较基准与当前请求', 'Compare baseline and current')}</button><button id="ax-restore">${tr('恢复基准为当前请求', 'Restore baseline as current')}</button><div id="ax-comparison"></div></details><details><summary>${tr('完整原始请求', 'Full original request')}</summary>${pretty(report.raw)}</details>`;
      const wire = () => {
        result.querySelectorAll('[data-inspect-node]').forEach(button => button.onclick = () => { index = Number(button.dataset.inspectNode); if (index < 0) return; result.querySelector('#ax-inspection').innerHTML = requestOverview(report, index); wire(); });
        result.querySelectorAll('[data-inspect-kind]').forEach(button => button.onclick = () => { index = report.items.findIndex(i => i.kind === button.dataset.inspectKind); result.querySelector('#ax-inspection').innerHTML = requestOverview(report, index); wire(); });
      };
      wire();
      result.querySelector('#ax-restore')?.addEventListener('click', () => { capture(); const original = source; source = other; other = original; parse(); loadContextWorkbench(); });
      result.querySelector('#ax-compare')?.addEventListener('click', () => { other = result.querySelector('#ax-other').value; result.querySelector('#ax-comparison').innerHTML = comparison(); });
    };
    refreshReport();
    body.querySelector('#ax-associate')?.addEventListener('click', () => {
      other = body.querySelector('#ax-stream-request').value;
      try { body.querySelector('#ax-associated').innerHTML = pretty(associateStream(report, other)); }
      catch (e) { body.querySelector('#ax-associated').textContent = e.message; }
    });
    body.querySelector('#ax-parse').onclick = () => { capture(); parse(); loadContextWorkbench(); };
    body.querySelector('#ax-example').onclick = () => { loadExample(); loadContextWorkbench(); };
    body.querySelector('#ax-protocol').onchange = e => { capture(); protocol = e.target.value; report = null; loadContextWorkbench(); };
    body.querySelector('#ax-clear').onclick = () => { source = ''; other = ''; report = null; error = tr('已清空。可以粘贴新输入或载入教学示例。', 'Cleared. Paste new input or load a teaching example.'); loadContextWorkbench(); };
    for (const action of ['system','tools']) body.querySelector('#ax-omit-' + action)?.addEventListener('click', () => {
      capture();
      try { const original = inspectRequest(source, protocol); other = source; let copy = action === 'system' ? stripInstructions(original.raw, protocol) : JSON.parse(source); if (action === 'tools') delete copy.tools; source = JSON.stringify(copy, null, 2); parse(); if (report) report.warnings.push('Edited copy: tool definitions or instructions may be missing. No model output is predicted.'); loadContextWorkbench(); } catch (e) { error = e.message; loadContextWorkbench(); }
    });
    body.querySelector('#ax-file').onchange = async e => {
      const file = e.target.files[0]; if (!file) return;
      if (file.size > (mode === 'stream' ? 2 : 1) * 1024 * 1024) { error = 'File exceeds size limit'; loadContextWorkbench(); return; }
      source = await file.text(); parse(); loadContextWorkbench();
    };
  }
  container.querySelectorAll('[data-ax-mode]').forEach(button => button.onclick = () => {
    const editor = container.querySelector('#ax-source'); if (editor) source = editor.value;
    const next = button.dataset.axMode;
    if (next !== 'lesson' && next !== lastDataMode) { source = ''; other = ''; report = null; error = ''; }
    if (next !== 'lesson') lastDataMode = next;
    mode = next; if (mode !== 'lesson') { report = null; if (source) parse(); } loadContextWorkbench();
  });
}
// Imported data never persists across reloads or identity changes.
window.addEventListener('aif:auth-changed', () => { source = ''; other = ''; report = null; error = ''; });
