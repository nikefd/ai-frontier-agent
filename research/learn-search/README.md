# Article-search reproduction for CS2680 stage 1

Original isolated teaching fixture inspired by the site's article-search use case. It is not an official Harvard task or the whole production search implementation. Baseline intentionally contains failing tests.

Expected behavior: literal substring search over original and translated title/summary, Unicode NFKC plus case folding through lower-case conversion, one result per nonempty string ID, preserve first matching row order, skip malformed rows, empty queries return nothing, never mutate input. No external dependencies or real user data.

Run `node --test search.test.mjs`. Controlled agents may edit only search.mjs.

## Controlled capture

`scripts/capture_learning_run.py --allow-agent-run --provider-config <explicit config path>` prepares a copy under the ignored `.run/learn-captures/` directory. The provider file may be JSON with an `env` object, or a dotenv file containing `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN` or `DEEPSEEK_API_KEY`. Only these provider values and `ANTHROPIC_BASE_URL` are read; hooks and unrelated values are never executed or copied.

The child process receives the credential in memory, uses `deepseek-flash` through DeepSeek's Anthropic-compatible endpoint and a fresh isolated `CLAUDE_CONFIG_DIR`, and captures actual CLI JSONL. No secret is placed in arguments or printed by the script. Missing configuration fails before any agent starts. Budget/turn/time limits apply; the CLI cost field is not independently verified DeepSeek billing.

A subsequent explicitly authorized invocation may use `--resume-capture <our previous capture directory>` to resume exactly that newly created session. It retains the controlled workspace and CLI configuration directory, disables editing and delegation for the follow-up, and rechecks tests. The script never scans private session histories and never publishes raw traces automatically.

Each invocation still needs user authorization; `--allow-agent-run` is a guard, not an authorization grant. Provider compatibility reference: https://api-docs.deepseek.com/guides/anthropic_api/ .
