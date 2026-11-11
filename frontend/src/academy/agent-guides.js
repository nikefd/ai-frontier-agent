import { escapeHtml as esc } from '../util.js';
import { tr } from '../context-panels.js';
import { componentExplanation } from './agent-components.js';
const p=(zh,en)=>[zh,en];
const l=value=>tr(...value);
export const agentGuides={
 'claude-code':{
  files:['CLAUDE.md','.claude/skills/<name>/SKILL.md','MCP / hooks'],
  mechanism:p('Claude Code 在“收集上下文 → 行动 → 验证”之间循环。读取文件获得证据，编辑和终端工具改变环境，再把结果放入下一轮上下文。任务不同，循环经过的工具和轮数也不同。','Claude Code cycles through context gathering, action and verification. File reads supply evidence, tools change the environment, and results inform later turns. Tools and turn counts depend on the task.'),
  guidance:p('CLAUDE.md 提供项目指导；skill 的 SKILL.md 描述用途与执行流程，还可引用脚本和资料。skill 是可复用的任务知识，工具才是实际读文件或执行命令的接口；不能把两者当成同一种 API 字段。','CLAUDE.md provides project guidance. SKILL.md describes reusable procedures and may reference scripts/resources. Skills supply task knowledge; tools expose operations. They are not one universal API field.'),
  pitfall:p('“工具有定义”不代表执行过；“助手说完成”也不代表验证成功。学习时应检查权限决策、工具实际返回及测试证据。长会话中的压缩还会改变后续模型看见的历史。','A tool schema does not prove execution, and an assistant saying done does not prove verification. Inspect permissions, actual results and test evidence. Compaction can change the history supplied later.'),
  source:'https://code.claude.com/docs/en/how-claude-code-works',extra:'https://code.claude.com/docs/en/skills',
 },
 codex:{
  files:['AGENTS.md','AGENTS.override.md','sandbox / approval policy'],
  mechanism:p('Codex 将任务、项目指令、已读取文件和工具历史组合为模型输入。模型选择下一步，运行环境执行读取、编辑或命令，返回结果后继续循环；最终结论应对应实际修改与验证证据。','Codex combines tasks, project instructions, inspected files and tool history into model input. The runtime executes reads, edits and commands, returns results, and continues. Conclusions should match actual changes and verification.'),
  guidance:p('指导文件按作用域组合：全局设置与从项目根到当前目录的指令形成指令链；存在 override 时优先读取 override。目录更深的规则会影响局部工作。AGENTS.md 是应用加载的指导，不是模型自动读取整个仓库。','Guidance combines global scope and the project-root-to-working-directory chain. Override files take precedence; deeper guidance affects local work. The app loads these instructions; the model does not automatically read the repository.'),
  pitfall:p('沙箱控制进程能访问什么，审批控制哪些动作需要确认，提示词只负责表达意图。即使模型提出一条命令，也可能被运行环境拒绝；需要保留拒绝、失败与后续修正的记录。','The sandbox controls process access and approval policy controls confirmation. Prompts express intent. A proposed command may be rejected; keep rejection, failure and correction evidence.'),
  source:'https://learn.chatgpt.com/docs/agent-configuration/agents-md',extra:'https://learn.chatgpt.com/docs/sandboxing',
 },
 'gemini-cli':{
  files:['~/.gemini/GEMINI.md','workspace / JIT GEMINI.md','/memory show'],
  mechanism:p('Gemini CLI 把模型与本地工具、扩展连接起来。先加载适用上下文，再根据模型请求执行工具，将 functionResponse 等结果放回历史；模型本身不拥有终端或文件系统权限。','Gemini CLI connects the model to local tools and extensions. It loads applicable context, executes requested tools, and returns results in history. The model itself does not own terminal or filesystem permissions.'),
  guidance:p('GEMINI.md 分全局、工作区/环境与按需 JIT 三类来源。工具访问文件目录时可发现局部指导。/memory show 可以检查已加载的上下文；修改磁盘文件不等于所有会话立即采用了新内容。','GEMINI.md comes from global, workspace/environment and just-in-time sources. File access can discover local guidance. /memory show inspects loaded context; editing disk content is not proof every session reloaded it.'),
  pitfall:p('要区分用户原始问题与 role=user 中承载的工具结果；后者不是新的真实用户指令。工具确认、扩展和上下文配置会改变执行路径，通用 Gemini API 示例不能冒充完整 CLI 抓包。','Distinguish human questions from tool results carried in role=user. The latter are not new human instructions. Confirmations, extensions and context settings affect execution; a generic API fixture is not a CLI capture.'),
  source:'https://geminicli.com/docs/cli/gemini-md/',extra:'https://github.com/google-gemini/gemini-cli',
 },
 'tool-loop':{
  files:['tool schema','call ID + arguments','tool result'],
  mechanism:p('模型先根据 schema 生成调用名称与参数。应用校验参数并执行操作，得到结果后用同一调用 ID 回填，模型才能在下一轮基于结果继续回答。一次模型输出也可能包含多个并行调用。','The model proposes names and arguments from schemas. The app validates and executes, then returns results under matching call IDs. Only the next turn can use them. A single output may contain parallel calls.'),
  guidance:p('schema 描述接口契约，工具实现包含实际代码与依赖，运行结果属于具体一次执行。这三层应分别检查。调用 ID 解决关联，原始顺序用来判断结果在模型哪一轮可见。','Schemas define contracts, implementations own code/dependencies, and results belong to specific executions. Inspect them separately. IDs associate calls/results; ordering establishes when results become visible.'),
  pitfall:p('缺失结果、重复 ID、非 JSON 参数或错误返回都不能静默当成功。外部工具内容是待核验数据，不能仅因为来自工具就提升成 system 指令。','Missing results, duplicate IDs, malformed arguments and errors must remain visible. External tool content is data to check, not automatically system-level instructions.'),
  source:'https://developers.openai.com/api/docs/guides/function-calling',
 },
 rag:{
  files:['document chunks','embedding index / retriever','selected evidence'],
  mechanism:p('文档先分块并建立检索索引。收到问题后，检索器选出相关片段，可再经过 reranker 精排，最后只把选中的片段放进模型请求。记忆库可以很大，本轮上下文仍然有限。','Documents are chunked and indexed. A retriever selects passages for a query, optionally reranked, then only selected evidence enters the model request. A large memory store does not imply a large current context.'),
  guidance:p('检索是应用层的数据选择步骤，可由普通代码触发，也可作为模型工具。案例使用 retrieve_memory 展示回填结构；它没有运行真实向量库，也没有暗中读到学习者资料。','Retrieval is application-level selection, invoked by ordinary code or a model tool. The retrieve_memory fixture illustrates result inclusion; it does not run a vector store or read personal learner data.'),
  pitfall:p('召回相关不代表证据正确。未检索到的内容、权限不允许的内容、过期记录都不应被声称已被模型看见；要检查来源、时间、引用片段和空召回处理。','Relevance is not truth. Do not claim unseen, inaccessible or stale records were available to the model. Check sources, dates, excerpts and empty-retrieval handling.'),
  source:'https://developers.openai.com/api/docs/guides/retrieval',
 },
 handoff:{
  files:['task / selected context','agent-as-tool or handoff','returned summary / state'],
  mechanism:p('子 Agent 作为工具与控制权交接是两种编排方式：前者完成子任务后把结果交回父任务，后者让接收者继续主会话。本案例是前者，只传入显式 task/context 并返回摘要。','Agent-as-tool and handoff differ: a nested specialist returns to its parent, while a handoff transfers the conversation. This fixture uses a nested tool with explicit task/context and a summary result.'),
  guidance:p('上下文共享取决于框架默认与过滤配置。例如 OpenAI Agents SDK 的 handoff 默认让接收者看到会话历史，可通过 input_filter 等改变；不能用本案例的最小参数推断所有真实 handoff 都只看到摘要。','Visibility depends on defaults and filters. OpenAI Agents SDK handoffs inherit conversation history by default; input_filter and other controls can change it. This minimal fixture does not describe every handoff.'),
  pitfall:p('名字里有 Agent 不会自动产生隔离。需要明确谁接收了哪些历史、工具结果和敏感字段；摘要也可能携带原始内容。停止条件、失败传播和预算由编排器管理。','An agent name does not create isolation. Specify which history and tool results recipients receive; summaries may retain original content. The orchestrator owns termination, failure propagation and budgets.'),
  source:'https://openai.github.io/openai-agents-python/handoffs/',
 },
 langgraph:{
  files:['State','Nodes + edges','Checkpointer / interrupt'],
  mechanism:p('LangGraph 用共享 state、节点和边表达执行流程。节点可以是普通代码、工具或模型；边决定下一节点。只有模型节点实际接收到的 state 子集属于模型上下文，不是整个图都自动进入 prompt。','LangGraph represents execution through state, nodes and edges. Nodes may be code, tools or models; edges choose what runs next. Only the state supplied to a model node becomes its context.'),
  guidance:p('框架提供持久执行、流事件、检查点和人工中断等机制，但不规定唯一 Agent 架构。检查点用于暂停/恢复执行状态，长期 memory store 与线程内 state 也应分别理解。','The runtime offers durable execution, streaming, checkpoints and interrupts without prescribing one agent architecture. Checkpoints restore execution state; long-term stores and thread state differ.'),
  pitfall:p('恢复执行不等于模型永远记住全部历史。还要确认节点是否有副作用、重试是否重复写入、错误如何路由。本页失败恢复案例解释通用原则，没有执行 LangGraph 实例。','Resuming a graph is not permanent model memory. Consider side effects, duplicate writes on retry and error routes. The linked fixture teaches recovery principles without running LangGraph.'),
  source:'https://docs.langchain.com/oss/python/langgraph/overview',
 },
};
export function agentGuidePanel(agent) {
 const guide=agentGuides[agent.id];
 return `<p><a class="ax-open-inspector" href="/runtime?lang=${document.documentElement.lang==='en'?'en':'zh'}">${tr('用真实运行日志检查这些机制 →','Inspect these mechanisms in a real trace →')}</a></p><h3>${tr('具体怎样工作','How it works in practice')}</h3><p>${esc(l(guide.mechanism))}</p><h3>${tr('关键文件与数据','Key files and data')}</h3><div class="ax-artifacts">${guide.files.map(file=>`<code>${esc(file)}</code>`).join('')}</div><p>${esc(l(guide.guidance))}</p><div class="ax-exercise"><b>${tr('容易误解的边界','A boundary to understand')}</b><p>${esc(l(guide.pitfall))}</p></div><p>${tr('依据官方公开资料整理，核验于 2026-11-11；不是产品的逐字 prompt 或真实会话导出。','Based on public official documentation, checked 2026-11-11; not a verbatim product prompt or captured session.')}</p><p><a href="${guide.source}" target="_blank" rel="noopener noreferrer">${tr('工作机制文档 ↗','Mechanism reference ↗')}</a>${guide.extra?` · <a href="${guide.extra}" target="_blank" rel="noopener noreferrer">${tr('配置与边界文档 ↗','Configuration reference ↗')}</a>`:''}</p>`;
}
const productFlow=[
 [p('任务、目录与指导文件','Task, working directory and guidance files'),p('适用指令和按需加载的资源','Applicable instructions and loaded resources'),p('只有实际加载的文字对模型可见；路径本身不包含文件全文。','Only loaded text is visible; a path does not include file contents.')],
 [p('指令、历史、工具 schema 和当前任务','Instructions, history, schemas and task'),p('文本、工具调用名称与参数','Text, tool names and arguments'),p('模型不能直接观察进程结果，需要运行环境回填。','The model cannot directly observe processes; the runtime must return results.')],
 [p('调用名称、参数与目标资源','Call name, arguments and target resource'),p('读取内容、变更结果、stdout / stderr','Read content, changes, stdout / stderr'),p('接口定义对模型可见；工具实现和全部磁盘内容不会自动进入上下文。','Schemas are visible; implementation code and the whole disk are not automatically context.')],
 [p('命令、写入目标与当前权限策略','Commands, write targets and permission policy'),p('执行、拒绝或确认决策','Execution, rejection or confirmation'),p('权限由应用或沙箱实际约束；提示词不能代替它。','The app/sandbox enforces access; instructions cannot substitute for enforcement.')],
 [p('工具结果、测试输出与会话历史','Tool results, tests and history'),p('下一轮请求、修正或最终结论','Next request, correction or conclusion'),p('验证证据必须实际回填，未执行的测试不能宣称通过。','Verification must be supplied; tests that were not run cannot be called passing.')],
];
export function agentComponentPanel(agent,index) {
 const row=agent.type==='product'||agent.id==='tool-loop'?productFlow[index]:null;
 return `<h3>${esc(l(agent.components[index]))}</h3><p>${esc(componentExplanation(agent,index))}</p>${row?`<dl class="ax-component-io"><dt>${tr('输入','Input')}</dt><dd>${esc(l(row[0]))}</dd><dt>${tr('输出','Output')}</dt><dd>${esc(l(row[1]))}</dd><dt>${tr('上下文可见性','Context visibility')}</dt><dd>${esc(l(row[2]))}</dd></dl>`:`<p>${esc(l(agentGuides[agent.id].guidance))}</p>`}<p>${tr('观察方法：在下方关联案例中，选择对应步骤并检查原始字段和新增内容。','To inspect: open the related lesson, select a step and examine the actual fields and additions.')}</p>`;
}
