import { tr } from '../context-panels.js';
export function componentExplanation(agent, index) {
  const specific = {
    rag: [
      ['用户问题驱动检索，不是把整个资料库放入提示词。','The question drives retrieval; the whole store is not placed in the prompt.'],
      ['检索请求指定关键词或向量查询，应用决定检索策略。','A retrieval request specifies keywords or a vector query; the app chooses the strategy.'],
      ['资料库在模型上下文之外，可能包含文档、索引或持久记忆。','The store is outside model context and may hold documents, indices or persistent memory.'],
      ['选择的片段作为数据进入上下文，需要保留来源并处理不可信内容。','Selected snippets enter context as data, with sources and untrusted-content handling.'],
      ['回答应可回溯到已提供的证据；检索失败时不能凭空补齐。','Answers should trace to supplied evidence; retrieval failure does not justify invented facts.'],
    ],
    handoff: [
      ['父任务由编排器拆分，交接范围需要明确。','The orchestrator decomposes the parent task and defines the delegation scope.'],
      ['交接接口表达任务和输入边界，不等于自动共享全部历史。','The handoff interface defines task and input boundaries, not automatic full-history sharing.'],
      ['编排器选择传入哪些上下文；可能传摘要、文件或部分消息。','The orchestrator selects context: a summary, files or selected messages.'],
      ['子Agent有自己的任务执行过程，是否继承工具与权限取决于实现。','A sub-agent runs its own task; tool and permission inheritance is implementation-dependent.'],
      ['返回结果需要由父Agent核验、整合；摘要不代表全部工作已验证。','The parent validates and integrates results; a summary alone does not verify the work.'],
    ],
    langgraph: [
      ['状态表示工作流当前数据，不等于全部都会被发送给模型。','State holds workflow data; not all state is necessarily sent to a model.'],
      ['节点可以是模型、工具或普通代码，每类节点有自己的输入输出。','Nodes may be models, tools or ordinary code, each with its own inputs and outputs.'],
      ['路由决定下一步节点，可由条件或模型结果驱动。','Routing chooses the next node using conditions or model outputs.'],
      ['工具节点由应用执行，仍需校验参数、权限和错误。','The application executes tool nodes and validates arguments, permissions and errors.'],
      ['持久化和恢复由框架/应用配置管理，不等于模型永久记住内容。','Persistence and recovery are configured by the framework/app, not permanent model memory.'],
    ],
  };
  const common = [
    ['指导文件与任务指令由应用加载，实际进入上下文的内容依实现和配置。','The app loads guidance and task instructions; inclusion depends on implementation and configuration.'],
    ['模型读取提供的上下文，生成文本或调用；它不是文件系统和执行环境。','The model reads supplied context and generates text or calls; it is not the execution environment.'],
    ['工具接口描述能力；实现代码和执行结果由应用或工具服务管理。','Tool interfaces describe capabilities; the app or tool service owns implementation and results.'],
    ['权限、沙箱或执行器形成实际边界，不能只依赖提示词约束。','Permissions, sandboxes and executors establish boundaries; prompts alone are insufficient.'],
    ['结果与历史进入后续请求，停止、错误处理和持久化依实现。','Results and history enter later requests; stopping, error handling and persistence vary.'],
  ];
  return tr(...(specific[agent.id] || common)[index]);
}
