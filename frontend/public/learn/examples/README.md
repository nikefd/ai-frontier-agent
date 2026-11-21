# Claude Code 启动失败记录

2026-11-16，经用户授权在独立代码复现目录启动 Claude Code 2.1.283 采集。
退出码1、未超时，返回未登录；无工具执行或文件修改，复现测试保持原状。

公开 JSONL 是人工审查的白名单字段：初始化类型/模型配置/工具名、错误文本、结果标记与CLI报告数字。删除路径、会话/消息标识、账号来源和其它元数据。初始化model与tools不是实际模型调用或工具执行的证明。is_error=true优先于同记录里的subtype=success。

这里只用于观察启动/失败边界，不代表编码修复、续问、子任务或课程作业已完成。

## search-repair.jsonl 与 search-artifacts.json

2026-11-16，以 Claude Code 2.1.283 客户端连接 DeepSeek Flash，先实际修复原创文章检索复现，再使用同一新建 session 与目录续问。两次CLI退出0、未超时，测试文件保持不变；独立测试从2通过/5失败变为7通过，续问后仍7通过，代码diff未再次改变。

原始两次stdout为1092和22条。公开21条经审查的初始化/可见文字/工具请求与结果/结束记录；删除思考块、估计思考token事件及无关账号元数据，路径和标识匿名化。每条 capture_source_line 对应 capture_segment 内的原采集行号。不是完整stdout，也不是API请求级捕获。工具输入/输出实际来自运行；测试与diff另为独立采集产物。

本次配置实际只暴露Bash、Edit、Read，未产生子任务。助手也明确报告无法调用reviewer；不能把这份记录当真实子任务树验收。CLI报告的费用数字未独立核验为DeepSeek账单。

## search-child.jsonl / search-child-artifacts.json

2026-11-16 在独立练习目录中使用 Claude Code 2.1.325、DeepSeek Flash、`--safe-mode` 实际运行并续问同一会话。原始 stdout 分别1423与435条；公开28条审查后事件。一次内置 Explore 委派、两次子任务 Read；父调用收到报告后才执行 Edit。测试从2通过/5失败变为7通过，续问复核仍为7通过，测试未改，续问源码未改。保留历史 bare 案例供对照，不能将两次实验当作同一运行。

公开记录保留实际工具输入/结果、父子关系、匿名会话标识及原采集行号；删除思考块、思考计数事件、账号元数据与私有路径。仅审查过的原创练习文件可公开；原始日志仍被忽略。费用为CLI报告值，未经DeepSeek账单核验。测试未覆盖空白ID等所有边界，模型的总结不替代测试。网页只回放，不启动CLI。

## http-repair.json / http-skill.json（2026-11-17）

新增真实HTTP正文采集，不与旧的九步CLI导读混成同一运行。Claude Code 2.1.325通过127.0.0.1随机端口及随机路径的本机桥转发到官方api.deepseek.com/anthropic；只保存请求JSON/响应正文，不保存或公开认证头。原始日志仅在忽略目录，公开版本经过审查。

- repair：safe-mode新隔离修复实验，7次实际请求，其中3/4为Explore子任务。测试文件未改，独立测试从2通过5失败变为7通过。公开System正文、工具input_schema、每轮Messages和响应。
- skill：新的只读插件实验，自己的search-check:verify-search，标准模式、空setting-sources、禁用hooks、独立CLI配置、严格空MCP。共5次请求；请求1的响应实际调用Skill，请求2的Messages实际包含注入的SKILL.md正文。原练习文件未变、测试2通过5失败，未声称修复。模型还请求列目录，该命令不在预授权测试命令中；记录保留实际反馈。
- 中间另做过一次bare Skill尝试，未提供Skill工具；失败尝试仅保留忽略目录，不冒充成功采集。

公开处理：移除request.metadata与客户端计费元数据；替换私有路径与调用标识；删除thinking/redacted_thinking内容及signature。SSE文本和参数增量先按块合并，再对完整字符串/JSON脱敏，避免路径跨片段造成漏删；公开事件保留块索引与capture_merged_deltas计数，不保留原始分片边界。提供方usage保留为报告值，非独立账单核验。系统提示词和Schema来自实际请求，不是根据工具名补写。Skill原文为本项目自己的原创练习。仅点击回放，不产生模型调用。

## http-normal.json（2026-11-21，默认正常多轮案例）

三次真实用户请求，通过Claude Code + DeepSeek Flash在同一新会话中完成；三轮分别实际启动CLI并使用同一session/config/workspace续问。共7个HTTP请求，分组为3+2+2，明确不把工具循环次数当成用户轮次。任务为读取原创教学条目、整理4篇入门清单、按第二轮偏好收窄到评估/记忆3篇、按第三轮要求生成三天阅读计划。没有故障注入或失败测试；源articles.json未改，工具反馈无错误。条目及阅读时长为教学输入，不是真实新闻或实时抓取。

独立核验：首轮表格IDs为A1/A3/A2/A4，第二轮为A3/A2/A4，第三轮计划沿用A3/A2/A4，每天15/18/20分钟；保留每轮实际assistant回复及文件快照。所有续问首个请求都实际包含此前用户请求，不是将三次独立单轮拼接。HTTP正文按前述规则脱敏并合并SSE增量，认证头未采集、思考内容未公开。CLI session原标识仅留忽略目录，公开标记为same-new-isolated-session。请求说明为人工审查导读，原始角色消息与模型回复不预写。

复现：`python -m scripts.capture_learning_conversation --allow-agent-run --provider-config /path/to/settings.json`，仅在获得受控模型运行授权后使用。运行只开放Read/Write/Edit，safe-mode/严格空MCP/独立CLI配置，不执行Bash、联网工具或子任务；raw产物不自动公开。网页仍只回放与导出到Inspector，不运行模型。
