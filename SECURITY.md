# 安全政策

## 支持范围

安全修复以 `main` 分支最新版本为准。自托管者需要自行保护环境变量、数据卷、反向代理和 RSSHub 的 Twitter 登录凭证。

## 报告漏洞

仓库公开后，请优先使用 GitHub 的 **Private vulnerability reporting** 提交问题，不要在公开 Issue 中披露漏洞细节、真实用户数据、访问令牌或可直接利用的完整攻击链。

报告应尽量包含：受影响版本、复现条件、实际影响、最小复现和建议修复方向。收到报告后会先确认影响范围，再协调披露时间。

## 明确不应提交的内容

- `AIF_LLM_API_KEY`、`DEEPSEEK_API_KEY`、`TWITTER_AUTH_TOKEN`
- SMTP 密码、会话签名密钥和认证 cookie
- `<data_dir>/auth/`、`<data_dir>/users/` 或生产数据卷内容
- 包含真实用户文章、画像、实验记录或对话的诊断包
