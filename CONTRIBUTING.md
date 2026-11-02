# 贡献指南

感谢帮助 AI Frontier Agent 改进信源覆盖、内容质量和实践体验。

## 开始之前

1. 先阅读 `AGENTS.md`、`llmdoc/index.md` 和 `llmdoc/overview/`。
2. 根据 `llmdoc/index.md` 的快速导航阅读所改模块文档。
3. 不提交 API Key、cookie、生产域名、邮箱、运行数据或用户产物。

## 本地验证

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest

cd frontend
npm ci
npm run build
npm audit --audit-level=high
```

涉及 Dockerfile 或依赖安装时，再执行 `docker build -t ai-frontier-agent:local .`。

## 提交约定

- 一个提交只解决一件事，格式为 `<scope>: <中文描述>`。
- 新增信源必须说明它为什么重要、是否为一手来源、更新时间及失败降级方式。
- 修改抓取、排序、鉴权或存储时必须补回归测试并同步 llmdoc。
- 不要用抓取时间冒充原始发布时间，也不要把热度直接等同于重要性。

代码贡献按本项目 Apache-2.0 许可提交。请确保有权贡献相应代码，并保留任何第三方许可和版权声明；见 `LICENSE` 与 `THIRD_PARTY_NOTICES.md`。
