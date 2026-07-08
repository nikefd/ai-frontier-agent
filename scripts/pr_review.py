"""AI PR review bot — DeepSeek + the repo's own review skill.

Runs inside GitHub Actions (see .github/workflows/pr-review.yml). Reads the
review standards from .claude/skills/pr-review/SKILL.md at runtime, so the
skill file stays the single source of truth — edit the skill, not this script.

Incremental review: the bot's previous comment carries a hidden marker with the
last-reviewed SHA; on new commits only the delta gets reviewed. The marker is
appended by THIS script (not left to the model), so incrementality never
depends on the model following instructions.

Stdlib only — no pip install step needed on the runner.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request

MARKER = "<!-- aif-pr-review -->"
SHA_RE = re.compile(r"审查截止[:：]\s*`?([0-9a-f]{7,40})`?")
DIFF_BUDGET = 50_000       # chars of diff fed to the model
DOC_BUDGET = 3_000         # chars of llmdoc index for project context

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"


def sh(*args: str) -> str:
    return subprocess.run(args, capture_output=True, text=True, check=False).stdout


def read_file(path: str, budget: int | None = None) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        return text[:budget] if budget else text
    except OSError:
        return ""


def last_reviewed_sha(repo: str, pr: str) -> str | None:
    """Find the newest bot comment's 审查截止 SHA (via gh api, GH_TOKEN injected)."""
    out = sh("gh", "api", f"repos/{repo}/issues/{pr}/comments", "--paginate")
    try:
        comments = json.loads(out)
    except json.JSONDecodeError:
        return None
    sha = None
    for c in comments:  # paginated list is oldest→newest; keep the last match
        body = c.get("body") or ""
        if MARKER in body:
            m = SHA_RE.search(body)
            if m:
                sha = m.group(1)
    return sha


def build_diff(base: str, head: str, last_sha: str | None) -> tuple[str, str]:
    """Return (diff, range_label). Prefer incremental from last reviewed SHA."""
    if last_sha:
        # Only usable if that SHA still exists (force-push invalidates it).
        if subprocess.run(["git", "cat-file", "-e", f"{last_sha}^{{commit}}"],
                          capture_output=True).returncode == 0:
            diff = sh("git", "diff", f"{last_sha}..{head}")
            if diff.strip():
                return diff, f"{last_sha[:7]}..{head[:7]}"
            return "", ""  # no new changes since last review
    diff = sh("git", "diff", f"{base}...{head}")  # three-dot: merge-base diff
    return diff, f"base..{head[:7]}"


def call_deepseek(api_key: str, system: str, user: str) -> str:
    payload = json.dumps({
        "model": "deepseek-chat",
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": 0.2,
        "max_tokens": 2500,
    }).encode("utf-8")
    req = urllib.request.Request(
        DEEPSEEK_URL, data=payload,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def post_comment(repo: str, pr: str, body: str) -> None:
    subprocess.run(
        ["gh", "api", f"repos/{repo}/issues/{pr}/comments",
         "-f", f"body={body}"],
        check=True)


def main() -> int:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    repo = os.environ["REPO"]
    pr = os.environ["PR_NUMBER"]
    base = os.environ["BASE_SHA"]
    head = os.environ["HEAD_SHA"]
    if not api_key:
        print("DEEPSEEK_API_KEY not set — skipping review")
        return 0

    last_sha = last_reviewed_sha(repo, pr)
    diff, range_label = build_diff(base, head, last_sha)
    if not diff.strip():
        print("no new changes to review — skipping")
        return 0
    truncated = len(diff) > DIFF_BUDGET
    diff = diff[:DIFF_BUDGET]

    skill = read_file(".claude/skills/pr-review/SKILL.md")
    comment_spec = read_file(".claude/skills/github-comment/SKILL.md")
    doc_index = read_file("llmdoc/index.md", DOC_BUDGET)

    system = (
        "你是这个仓库的自动 PR 审查机器人。严格遵循下面的审查规范和评论格式规范，"
        "用简体中文输出一条 GitHub 评论（Markdown）。只输出评论本身，不要额外解释。\n\n"
        f"=== 审查规范 ===\n{skill}\n\n"
        f"=== 评论格式规范 ===\n{comment_spec}\n\n"
        f"=== 项目背景（llmdoc 索引节选）===\n{doc_index}"
    )
    mode = "增量审查" if last_sha and range_label.startswith(last_sha[:7]) else "全量审查"
    user = (
        f"审查模式：{mode}；diff 范围：{range_label}；HEAD: {head}\n"
        + ("（注意：diff 因过大被截断，聚焦你能看到的部分）\n" if truncated else "")
        + f"\n=== DIFF ===\n{diff}"
    )

    try:
        review = call_deepseek(api_key, system, user)
    except Exception as e:  # noqa: broad-except — a broken review must not fail CI
        print(f"review failed: {e}")
        return 0

    # Footer appended by the script: incrementality must not depend on the model.
    body = f"{review}\n\n{MARKER}\n审查截止: `{head}`"
    post_comment(repo, pr, body)
    print(f"review posted ({mode}, {range_label})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
