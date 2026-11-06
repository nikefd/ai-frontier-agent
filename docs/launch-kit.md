# AI Frontier Agent 宣传文案包

以下是待发布草稿，按使用场景选一份即可。长帖适合介绍项目并收集反馈，短帖用于附演示链接。项目功能与限制以 [English README](../README.md) / [中文 README](../README.zh-CN.md) 为准。

## 一句话介绍

中文：一个可自托管的 AI 资讯阅读器，把分散的模型、API、开源和研究更新整理成带原文引用的中英双语速报。

English: A self-hosted AI news reader with source-linked daily briefings in English and Chinese.

## 中文社区长帖

### 标题

开源了一个 AI 资讯阅读器：中英双语速报、原文引用，支持自托管

### 正文

做了一个叫 AI Frontier Agent 的小项目，想解决的问题很直接：AI 更新分散在官方博客、API 更新日志、论文和社区里，读完标题还得自己判断哪些值得跟进。

它会把这些来源聚合到一个阅读器里，合并同一事件的相关报道，再生成带原文引用的每日速报。可以先看速报，再按兴趣打开原文、收藏或深入解读。

目前主要能做这些：

- 跟踪模型发布、API 变更、开源工具和研究，内置 116 个来源，按层级定时刷新。
- 界面可切换中文 / English，新生成的速报提供中英文两个版本，也可以通过 RSS 订阅。
- 查看来源健康和内容新鲜度，了解哪些来源抓取失败或长期没有更新。
- 登录后保存收藏，按需生成解读和实验卡，记录尝试结果。
- 用 Docker Compose 自托管，连接自己的兼容模型 API；代码采用 Apache-2.0 许可。

公开文章和速报不需要注册就能看：

- 中文速报：https://ai.zhangyangbin.com/summary?lang=zh
- 最新文章：https://ai.zhangyangbin.com/feed?lang=zh
- GitHub：https://github.com/nikefd/ai-frontier-agent

这是早期版本，来源会受限流或页面变化影响，AI 摘要也需要对照原文判断。英文文章模式展示原始标题和摘要，原文本来是中文时不会自动变成英文。自托管的模型调用费用由部署者承担。

想请经常跟进 AI 的朋友帮忙试一下：**看完一份速报后，有没有哪条值得打开原文？有没有明显重复、遗漏或说不清楚的地方？** 最好给一个具体例子，这样比较容易改。

## Show HN

### Submission title

Show HN: A self-hosted AI news reader with bilingual, source-linked briefings

### Submission URL

https://ai.zhangyangbin.com/summary?lang=en

### First comment

I built AI Frontier Agent to bring scattered AI updates into one place: model releases, API changelogs, open-source tools and research.

It groups related coverage and generates a daily briefing in English and Chinese, with numbered links back to the sources. The public briefing and article feed are readable without an account.

The project is self-hostable with Docker Compose and uses your own OpenAI-compatible model endpoint. It includes source health and freshness diagnostics, bookmarks, and optional deep dives and experiment cards. The code is Apache-2.0 licensed.

Demo: https://ai.zhangyangbin.com/summary?lang=en
Code: https://github.com/nikefd/ai-frontier-agent

A few limits: this is an early project, upstream feeds can fail, and generated summaries need checking against the sources. Source counts and health metrics do not prove complete coverage of the AI landscape. English mode uses original article titles and summaries; it does not translate every source or previously saved document into English. Self-hosters cover their own model API costs.

I'd appreciate concrete feedback: after reading a briefing, which item would you open, and which item feels redundant, unclear or missing? If you try self-hosting it, where does setup first become confusing?

## 中文短帖

做了一个开源 AI 资讯阅读器：把模型、API、开源工具和研究更新聚合成带原文引用的中英双语速报，支持 RSS 和 Docker 自托管。

欢迎试读一份，告诉我哪条值得点开、哪条重复或没讲清楚：
https://ai.zhangyangbin.com/summary?lang=zh

源码：https://github.com/nikefd/ai-frontier-agent

## English short post

I built an open-source AI news reader with source-linked daily briefings in English and Chinese. Self-host it with Docker and your own model API.

Try it: https://ai.zhangyangbin.com/summary?lang=en
Code: https://github.com/nikefd/ai-frontier-agent

What should I improve?

## 30 秒演示脚本

这是录制提纲，不是已录制的视频。中文和英文各录一遍，先用顶栏语言选择器切到对应语言。

| 时间 | 画面操作 | 中文口播 | English narration |
|---|---|---|---|
| 0–5 秒 | 打开今日速报 | AI 更新太分散，我做了一个把它们整理到一起的阅读器。 | AI updates are scattered. I built a reader to bring them together. |
| 5–13 秒 | 展示重点和一个引用链接，打开原文 | 先看一份速报，感兴趣的内容可以直接点回来源核验。 | Start with a briefing, then follow a citation to check the original source. |
| 13–21 秒 | 回到文章页，搜索一个实际存在的话题 | 想继续跟进，可以搜索文章、按来源筛选，再决定哪些值得深挖。 | Search the feed and filter sources to decide what deserves a closer look. |
| 21–27 秒 | 打开语言选择器，切换速报语言 | 界面和新速报支持中英双语。 | The interface and new briefings support English and Chinese. |
| 27–30 秒 | 展示 GitHub README 的部署入口 | 项目开源，也可以在自己的服务器部署。欢迎试用并告诉我哪里不好用。 | It's open source and self-hostable. Try it and tell me what needs work. |

录公开阅读页面即可，不需要在视频中登录、展示个人资料或调用 AI。配图可使用现有 [中文速报截图](images/daily-digest.png) / [英文速报截图](images/daily-digest-en.png)。截图内容会随版本变化，不作为准确性或完整召回的证明。

## 常见问题回复

**和普通 RSS 阅读器有什么不同？**

RSS 阅读器负责订阅和阅读；这个项目另外做了相关性过滤、相关事件聚合、双语速报与原文引用，也能查看来源健康。是否比你现有的阅读方式省事，欢迎用同一批信息对比。

**Does it run locally, and does it need an OpenAI key?**

You can self-host the app. AI features use the compatible endpoint and model you configure; the default is DeepSeek, so an OpenAI key is not required. Fetching and reading work without a model key. A local model endpoint is usable if it supports the required API and is reachable from the app container.

**全部免费吗？ / Is it free?**

代码采用 Apache-2.0；公开演示的文章和速报可以直接阅读。自托管者承担服务器和模型 API 成本。

The code is Apache-2.0 licensed, and the public demo's feed and briefings are readable without signup. Self-hosters pay their infrastructure and model-provider costs.

**Can I rely on it for complete coverage?**

No. It follows a configured source list, and upstream access and AI summaries can fail. The diagnostics help expose some of those limits. Use the original source when accuracy matters.

## 使用顺序

先选一篇中文长帖或英文 Show HN 草稿，小范围试读后再发另一个版本。发布前打开当天的速报，确认页面和引用可用；发出后保留时间回答问题。反馈优先记录具体页面、原文链接和期待行为，先处理影响阅读或部署的共性问题。

Show HN 版本按 [官方说明](https://news.ycombinator.com/showhn.html)准备：提交可直接体验的作品，说明自己做了什么，并参与讨论。不要请求朋友集中点赞或评论。其他社区使用各自合适的栏目与当时的发帖规则。

本文件没有代发任何帖子。下一步若决定发布，请指定平台和版本；未公开验证的用户量、节省时间、准确率和召回率不要加入文案。
