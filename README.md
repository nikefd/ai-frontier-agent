# AI Frontier Agent

**English** | [简体中文](README.zh-CN.md)

[![CI](https://github.com/nikefd/ai-frontier-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/nikefd/ai-frontier-agent/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)

**A self-hosted AI news reader that turns scattered updates into a daily briefing with links to original sources.**

Follow model releases, API changes, open-source tools and research. Read in English or Chinese, bring your own OpenAI-compatible model endpoint, and keep your bookmarks, experiments and conversations on your own server.

[Live demo](https://ai.zhangyangbin.com/?lang=en) · [Daily briefing](https://ai.zhangyangbin.com/summary?lang=en) · [Latest articles](https://ai.zhangyangbin.com/feed?lang=en) · [English RSS](https://ai.zhangyangbin.com/rss/digest.xml?lang=en)

[![Daily briefing with original-source citations](docs/images/daily-digest-en.png)](https://ai.zhangyangbin.com/summary?lang=en)

## What it does

- **Follow first-party updates.** 116 built-in sources across official releases, API changelogs, engineering blogs, papers and selected communities. Fast sources refresh hourly; regular and discovery sources refresh every 4 and 12 hours.
- **Read a concise daily briefing.** Related reports are grouped, sources are cited, and each generated briefing has English and Chinese versions. Subscribe through RSS.
- **Explore the details.** Generate deep dives and small experiment cards, save progress notes, and discuss articles with the assistant.
- **Inspect coverage.** See source health, freshness, filtering and discovery latency. Manually registered event benchmarks retain observed evidence even when articles leave the rolling feed.
- **Own your data.** Personal collections are isolated by user and stored in your data volume. A single FastAPI process serves the UI and scheduled jobs; no separate database server is required.

## Screenshots

**Article feed** — search, sort, read source summaries and open the original article.

[![Article feed with source categories and reading actions](docs/images/article-feed-en.png)](https://ai.zhangyangbin.com/feed?lang=en)

**Source health** — inspect the configured sources and understand coverage limits.

[![Source health and coverage overview](docs/images/source-health-en.png)](https://ai.zhangyangbin.com/sources?lang=en)

Screenshots show the public demo on 2026-11-04; the live content changes over time.

## Quick start with Docker Compose

Requires Docker and Docker Compose. Run these commands in an interactive terminal:

```bash
git clone https://github.com/nikefd/ai-frontier-agent.git
cd ai-frontier-agent
cp .env.example .env

# Optional: set AIF_LLM_API_KEY in .env. DeepSeek is the default endpoint.
# For another compatible provider, also set AIF_LLM_BASE_URL and AIF_LLM_MODEL.
docker compose build

# Create the first admin on the server. The password is entered privately.
docker compose run --rm --no-deps ai-frontier \
  python -m app.bootstrap_admin --email you@example.com --language en

docker compose up -d
```

Open [http://127.0.0.1:9702/?lang=en](http://127.0.0.1:9702/?lang=en), sign in and select **Fetch now**. A new instance starts with an empty feed. Initialize the admin before exposing the service publicly; web registration only creates regular users. Initialization refuses to replace an existing admin.

Compose starts the app, RSSHub and Redis. App data lives in the `ai-frontier-data` named volume and survives image upgrades. Linux/macOS support the native admin CLI; use the Docker terminal on Windows.

## Language support

Use the language picker in the top bar. The app remembers your choice in the browser; `?lang=en` and `?lang=zh` provide explicit shareable links. With no preference, the app uses the browser language, falling back to English.

English mode shows original article titles and summaries instead of their Chinese translations. Original source content may itself be in another language. New briefings are generated in both languages; new personal AI outputs follow the selected interface language. Existing notes, deep dives and other saved content keep their original language. Some source-authored descriptions and diagnostic details also retain their original text.

The [English RSS feed](https://ai.zhangyangbin.com/rss/digest.xml?lang=en) includes briefings with an English rendition. Historical Chinese-only briefings are retained in the [Chinese feed](https://ai.zhangyangbin.com/rss/digest.xml).

## Configuration and costs

| Variable | Purpose |
|---|---|
| `AIF_LLM_API_KEY` | Model key for enrichment, briefings, deep dives and chat; falls back to `DEEPSEEK_API_KEY` |
| `AIF_LLM_BASE_URL` / `AIF_LLM_MODEL` | Your OpenAI-compatible endpoint and model; defaults to DeepSeek |
| `AIF_SECRET_KEY` | Set a random session signing key for public deployments |
| `AIF_COOKIE_SECURE=1` | Enable for HTTPS deployments |
| `AIF_SMTP_*` / `AIF_PUBLIC_BASE_URL` | Email verification and password recovery for regular users |
| `TWITTER_AUTH_TOKEN` | Optional X credentials, passed only to your private RSSHub |

You pay your model provider directly. Fetching and browsing work without a model key; AI features require one. Bilingual briefings use one model request with two renditions and therefore more output tokens than a single-language briefing. Switching languages or reading cached content does not call a model. Some X sources require credentials; official feeds and API sources operate independently.

See [.env.example](.env.example). Detailed [configuration](llmdoc/reference/config-reference.md), [deployment](llmdoc/guides/how-to-deploy.md) and [backup/restore](llmdoc/guides/backup-and-restore.md) guides are currently in Chinese.

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# For local development, set AIF_RSSHUB_BASE=https://rsshub.app in .env.
(cd frontend && npm ci && npm run build)
python -m app.bootstrap_admin --email you@example.com --language en
uvicorn app.main:app --port 9702 --reload
```

Run `pytest` for the backend and `cd frontend && npm run build` for the frontend. UI translations are bundled with the app and require no translation service at runtime.

## Contributing

Useful contributions include reliable first-party source adapters, publication-date regression cases, deployment fixes and language improvements. Include a minimal fixture when changing a source parser. English and Chinese issue reports are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md), the [documentation index](llmdoc/index.md) and [security policy](SECURITY.md).

## Limits

Upstream availability depends on network access, rate limits, credentials and page changes. Coverage metrics describe configured sources and registered events; they do not measure recall across the whole web. Check AI summaries and experiment suggestions against the original source. Public hosting also requires reviewing the source content's terms and redistribution permissions.

## License

Original project software and documentation are licensed under [Apache-2.0](LICENSE). Dependencies and source content retain their own licenses and rights; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
