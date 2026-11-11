// Original instructional explanations: data flow differs by task, not brand.
export const taskGuides = {
  text: {
    title: ['文本、推理与工具循环','Text, reasoning and tool loops'],
    steps: [['指令 + 对话 + 工具定义','Instructions + history + tool schemas'],['模型生成文本或调用','Model emits text or a call'],['应用执行并回填结果','App executes and returns results']],
    learn: ['先在请求中找到高优先级指令，再区分工具定义、调用参数与工具返回。模型每轮读取的是实际传入的上下文，不是整个文件系统或账号里的全部历史。','Find instructions first, then distinguish schemas, call arguments and returned data. Each turn reads supplied context, not an entire filesystem or every account conversation.'],
    exercise: ['比较工具执行前后的两份请求，找出新增调用 ID 与结果，观察上下文字节为何增长。','Compare requests before and after a tool call. Locate the call ID and result, and explain the growth in context bytes.'], lesson:'notes',
  },
  image: {
    title:['图像生成与编辑','Image generation and editing'],
    steps:[['提示词 + 参考图','Prompt + reference image'],['生成 / 编辑接口','Generation / editing endpoint'],['图像与输出元数据','Image + output metadata']],
    learn:['这里的输入可能含图片或视频，不只是聊天 messages。图像的尺寸、质量、数量、参考图和编辑轮次都会影响结果与计费；多模态理解也不等于一定能生成图像。','Input may contain images or video, beyond chat messages. Size, quality, quantity, references and editing turns affect output and billing. Understanding images does not imply generating them.'],
    exercise:['拿一段编辑请求，分别标出文字约束、参考素材与生成参数；检查下一轮是否实际带回上一张图。','Label text constraints, reference assets and generation parameters in an edit request. Check whether the next turn actually includes the previous image.'],lesson:null,
  },
  audio: {
    title:['语音输入、转录与合成','Speech input, transcription and synthesis'],
    steps:[['文字 / 音频输入','Text / audio input'],['转录、TTS 或实时接口','Transcription, TTS or real-time API'],['文字 / 音频输出','Text / audio output']],
    learn:['先区分语音转文字、文字转语音和实时双向语音。三种任务的输入、输出、流事件及计费单位都可能不同，不能用同一张聊天 token 表比较。','Distinguish speech-to-text, text-to-speech and live bidirectional voice. They have different inputs, outputs, stream events and billing units. A chat token table does not compare them directly.'],
    exercise:['检查接口输出究竟是文字还是音频，以及价格按分钟、字符还是 token 计算。音频结果还应核对语言、采样率与格式。','Identify whether output is text or audio and whether pricing uses minutes, characters or tokens. Check language, sample rate and format.'],lesson:null,
  },
  video: {
    title:['视频生成与时间维度','Video generation and time'],
    steps:[['文字 + 参考帧 / 视频','Prompt + reference frames / video'],['生成任务与状态','Generation job + status'],['视频 / 音频与时长','Video / audio + duration']],
    learn:['视频生成通常有独立任务状态、时长和分辨率参数。可理解视频的语言模型与生成视频的模型是不同能力；秒数也不能当作文本上下文上限。','Video generation has job status, duration and resolution parameters. Video understanding and generation differ; seconds are not a text-context limit.'],
    exercise:['比较首帧生成、视频编辑和延长任务：分别观察参考素材、时间约束、返回任务状态以及最终媒体。','Compare first-frame generation, editing and extension: inspect references, temporal constraints, job status and final media.'],lesson:null,
  },
  embedding: {
    title:['向量检索：召回阶段','Embedding retrieval: candidate recall'],
    steps:[['文档切块 + 编码','Chunk documents + encode'],['索引与相似度检索','Index + similarity retrieval'],['检索片段进入上下文','Retrieved passages enter context']],
    learn:['embedding 输出一串数值，不直接回答问题。先把文档编码建立索引，再用兼容编码器处理查询，按相似度找到候选；只有选出的片段进入后续语言模型。','Embeddings produce vectors, not answers. Encode documents into an index and queries with a compatible encoder; similarity retrieves candidates. Only selected passages enter the language model.'],
    exercise:['检查索引与查询的模型版本、输出维度及归一化是否一致，再在记忆案例里定位实际回填的证据片段。','Check encoder versions, dimensions and normalization for index and query, then locate supplied evidence in the memory lesson.'],lesson:'memory',
  },
  reranker: {
    title:['重排：在召回结果中精排','Reranking: refine retrieved candidates'],
    steps:[['问题 + 候选文档','Query + retrieved candidates'],['逐对相关性评分','Pairwise relevance scoring'],['排序后选取证据','Rank + select evidence']],
    learn:['重排模型比较问题与每个候选文档，输出相关性分数。它通常接在向量召回后面，不能替代整个检索系统；分数表示相关性，也不保证文档事实正确。','A reranker scores each query/document pair. It follows retrieval rather than replacing the whole system. Relevance scores do not guarantee factual correctness.'],
    exercise:['先召回多份材料，再观察重排前后的顺序；区分“更相关”与“有来源、可验证”。','Retrieve several passages and compare their order after reranking. Distinguish relevance from sourced, verifiable evidence.'],lesson:'memory',
  },
};
export const modelGuide = model => taskGuides[model.task] || taskGuides.text;
