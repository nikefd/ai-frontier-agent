# 生产验收与独立样本

## 只读验收

在仓库根目录执行，目标地址由操作者提供，结果写入不入 Git 的 `.run/`：

```bash
.venv/bin/python -m scripts.production_audit https://your-domain.example \
  --samples evaluation/official-events-2026-10-31.json \
  --output .run/production-audit.json
```

工具只读取公开的 health、sources、quality/report、summary/today 和分页 articles，不触发抓取、LLM 或生产写入，也不需要登录。JSON 只保留健康版本、来源问题、质量计数、速报生成时间/年龄和独立样本匹配结果，不复制用户数据、health 中的磁盘路径或速报全文。

退出码 0 与 `ok=true` 表示 API 读取完整且 health.ok 为 true，**不表示所有来源健康或业务验收通过**；应继续检查 `quality.status`、`source_issues`、`summary.age_hours`、`registered_benchmarks` 与独立样本。任一端点失败时保留部分报告并退出 1；分页数量改变、重复或不完整时不评估样本，避免生成假缺口。各请求分时执行，不是服务器事务快照；发生并发更新时应复测。`version` 仅是应用版本，内容字段可用于能力验收，不能据此断言精确 Git SHA。

## 独立样本如何维护

先看官方发布栏目并按价值选取事件，再检查本站文章；不要从本站已抓文章反推样本。每项记录标题、官方原文 `source_url`、官网日期 `published_on`、核验日期 `verified_on` 与入选理由 `reason`。示例集合是人工挑选的模型/研究探针，不是随机样本或全面覆盖集合。

工具只按忽略 query/fragment/尾斜线的官方 URL 匹配。`observed` 表示原文在当前库；`not_observed` 表示没有观察到该官方 URL，不排除同事件的媒体报道、URL 迁移或滚动淘汰。库最多保留 400 篇，日期只精确到天，因此不把缺失判为历史漏报，也不计算小时级准时召回率。要持续评价，应定期运行并保留各时点报告；本工具不会自行安排定时任务。

## 正式必达基准的发现方式

数据源页手工登记时可选“从站外独立发现”或“普通手工登记”；自动候选加入时标记为“已抓候选”。API `origin=independent/manual/candidate`，旧基准缺省归入 manual。independent 必须提供来源 URL，真实性仍由管理员人工核验，服务端不会自动证明 URL 是官方。

公开质量报告 `benchmark_coverage.origin_breakdown` 分别给出 total/settled/on_time/missed。不要用 candidate 的命中情况代表站外独立样本的召回；正式基准已增加命中证据留存：登记/入库/富化/淘汰/启动时保存可确认的最早匹配，已保存命中不因文章淘汰消失。此前已经淘汰且未保存的命中仍无法恢复。示例集合的日期没有时分秒，不会自动写入正式基准或伪造精确发布时间。
