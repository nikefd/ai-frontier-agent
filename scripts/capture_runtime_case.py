"""Capture an explicitly authorized isolated CLI experiment; never publish logs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import sys
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.storage import write_json_atomic, write_text_atomic
PROMPT = (
    'Work only in this isolated directory. Read TRACE_RULES.md, boot.mjs and '
    'boot.test.mjs. Do not inspect any other directory or private configuration. '
    'Run node --test boot.test.mjs before editing. Fix only boot.mjs so public '
    'views render before auth without showing the landing hero; private views '
    'must still wait for auth. Never change tests. Run tests again and show the '
    'diff. Do not use subagents, network tools, install packages, commit or push.'
)


def execute(command: list[str], cwd: Path, timeout: int = 180) -> dict:
    process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True)
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(process.pid, signal.SIGINT)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
    return {'exit_code': process.returncode, 'stdout': stdout.decode(errors='replace'),
            'stderr': stderr.decode(errors='replace'), 'timed_out': timed_out}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent', choices=['codex', 'claude'], required=True)
    parser.add_argument('--allow-agent-run', action='store_true', help='Use only after explicit authorization')
    args = parser.parse_args()
    if not args.allow_agent_run:
        parser.error('Explicit authorization is required to start the CLI experiment.')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    destination = ROOT / '.run' / 'runtime-captures' / f'{stamp}-{args.agent}'
    workspace = destination / 'workspace'
    shutil.copytree(ROOT / 'research' / 'runtime-case', workspace)
    subprocess.run(['git', 'init', '-q'], cwd=workspace, check=True)
    subprocess.run(['git', 'add', '.'], cwd=workspace, check=True)
    tests_before = (workspace / 'boot.test.mjs').read_bytes()
    before = execute(['node', '--test', 'boot.test.mjs'], workspace)
    version = execute([args.agent, '--version'], workspace)
    if args.agent == 'codex':
        command = ['codex', 'exec', '--json', '--ephemeral', '--ignore-user-config',
                   '--sandbox', 'workspace-write', '-C', str(workspace), PROMPT]
    else:
        command = ['claude', '-p', PROMPT, '--output-format', 'stream-json', '--verbose',
                   '--safe-mode', '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
                   '--tools', 'Read,Edit,Write,Bash', '--allowedTools', 'Read,Edit,Write,Bash(node --test*)',
                   '--permission-mode', 'acceptEdits', '--max-turns', '16', '--max-budget-usd', '1',
                   '--no-session-persistence']
    result = execute(command, workspace)
    after = execute(['node', '--test', 'boot.test.mjs'], workspace)
    diff = execute(['git', 'diff', '--', 'boot.mjs', 'boot.test.mjs'], workspace)
    metadata = {'agent': args.agent, 'cli_version': version['stdout'].strip(), 'captured_at': stamp,
                'task': PROMPT, 'capture': 'CLI stdout only; not API wire traffic',
                'tests_unchanged': tests_before == (workspace / 'boot.test.mjs').read_bytes(),
                'trace_sha256': hashlib.sha256(result['stdout'].encode()).hexdigest(),
                'exit_code': result['exit_code'], 'timed_out': result['timed_out']}
    for name, value in [('before-tests.json', before), ('after-tests.json', after), ('diff.json', diff), ('manifest.json', metadata)]:
        write_json_atomic(destination / name, value)
    write_text_atomic(destination / 'trace.jsonl', result['stdout'])
    write_text_atomic(destination / 'stderr.txt', result['stderr'])
    print(json.dumps({'capture_directory': str(destination), 'exit_code': result['exit_code'],
                      'timed_out': result['timed_out'], 'tests_unchanged': metadata['tests_unchanged'],
                      'before_tests_exit': before['exit_code'], 'after_tests_exit': after['exit_code']}))


if __name__ == '__main__':
    main()
