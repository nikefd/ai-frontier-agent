const p=(zh,en)=>[zh,en];
export const lessonNotes={
 notes:[
  p('第一轮包含任务指令、search_notes 的参数定义和用户问题。此时还没有工具结果；模型能知道工具怎样调用，但不能凭 schema 得到笔记内容。','The first request contains instructions, the search_notes schema and the question. No result exists yet. A schema describes how to call a tool, not what the notes contain.'),
  p('下一轮保留原来的指令和问题，新增助手调用及对应结果。call_demo_1 把这两块关联起来。笔记文字只有被应用放进这轮请求后，才成为回答可用的证据。','The next request retains the original task and adds an assistant call plus its result. call_demo_1 links them. Notes become usable evidence only after the app includes them here.'),
 ],
 coding:[
  p('用户要求修复除零问题并验证。三个工具只是接口定义，还没执行。先读取文件才能知道真实实现；不要把工具列表误当成已经改过代码。','The task is to fix division by zero and verify. Three tools are defined but unexecuted. Reading the file supplies the implementation; a tool list is not evidence of a change.'),
  p('read_1 读取示例文件，结果暴露了直接 a/b 的实现。新增的是文件证据，不是修复完成。下一步需要生成修改，并让应用实际执行编辑。','read_1 returns the demo file containing a direct a/b implementation. This is evidence of the current code, not a completed fix. Editing is still needed.'),
  p('edit_1 带有除零检查的修改内容，应用返回 applied=true。这只能证明教学记录中的编辑被接受，尚无运行测试的证据。','edit_1 carries the zero-divisor guard and the app returns applied=true. This records an accepted edit in the fixture, with no test evidence yet.'),
  p('test_1 的结果新增 exit_code=0 和 passed=3。现在可以指向具体测试证据；也要保留测试范围，三个示例测试通过不代表所有真实场景都正确。','test_1 supplies exit_code=0 and passed=3. The conclusion now has test evidence, limited to three authored tests rather than every real-world case.'),
 ],
 recovery:[
  p('第一轮只有任务与工具定义。后续示例会故意提交一个空 query，用来学习错误结果如何进入上下文，而不是展示真实模型犯错率。','The first request defines the task and tool. The fixture deliberately uses an empty query next to teach error feedback, not to measure model error rates.'),
  p('failed_1 的 query 为空，tool_result 明确标出 is_error=true。错误内容必须保留，不能改写成成功。模型在这一轮能看到空参数为什么被拒绝。','failed_1 has an empty query and tool_result marks is_error=true. Keep the failure rather than rewriting it. This request makes the rejection reason visible to the model.'),
  p('retry_2 使用新的调用 ID 和非空 query，返回有效笔记。历史同时保留失败与成功；如果复用旧 ID，两个结果就可能发生歧义。','retry_2 uses a new ID and a non-empty query. Both failure and success remain in history; reusing an ID could make associations ambiguous.'),
 ],
 memory:[
  p('当前问题问虚构学习者选择的语言，记忆库并未自动出现。模型只看见 retrieve_memory 的定义与问题；指导文件和持久记忆也不是同一种东西。','The question asks for a fictional learner preference. The memory store is not automatically present; the model sees the retrieval schema and question. Guidance files and persistent memory are distinct.'),
  p('memory_1 的 functionResponse 提供 language=Chinese 及虚构来源。只有这一条片段被加入当前请求；检索不到的记忆不能被声称已读到。','memory_1 returns language=Chinese and a fictional source in functionResponse. Only this record enters context; unretrieved memories are not visible.'),
 ],
 handoff:[
  p('父任务要比较 tool 与 skill，delegate_research 的 schema 允许传 task 和 context。此时没有子任务结果，也没有证据表明任何子 Agent 已运行。','The parent task compares tools and skills. delegate_research accepts task and context, but no result or sub-agent execution evidence exists yet.'),
  p('delegate_1 显式传入子任务与允许使用的资料范围，返回 summary 和 evidence。本例是子任务作为工具后返回父任务，不是 SDK handoff 默认继承会话历史的演示。','delegate_1 supplies a task and allowed context and returns summary/evidence. This is a nested agent-as-tool returning to its parent, not a demonstration of SDK handoff history defaults.'),
 ],
};
