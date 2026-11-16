"""Explicitly authorized Claude Code / DeepSeek learning captures; no automatic publishing."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.storage import write_json_atomic, write_text_atomic
from scripts.capture_runtime_case import execute
CAPTURES=ROOT/'.run'/'learn-captures'
PROVIDER_KEYS={'ANTHROPIC_BASE_URL','ANTHROPIC_API_KEY','ANTHROPIC_AUTH_TOKEN','DEEPSEEK_API_KEY'}


def provider_environment(path: Path | None) -> dict:
    values={key:os.environ[key] for key in PROVIDER_KEYS if os.environ.get(key)}
    if path:
        if path.suffix=='.json':
            data=json.loads(path.read_text())
            supplied=data.get('env',{})
        else:
            from dotenv import dotenv_values
            supplied=dotenv_values(path)
        values.update({key:value for key,value in supplied.items() if key in PROVIDER_KEYS and isinstance(value,str) and value})
    key=values.get('ANTHROPIC_API_KEY') or values.get('ANTHROPIC_AUTH_TOKEN') or values.get('DEEPSEEK_API_KEY')
    if not key:
        raise ValueError('No provider credential found; no agent was started. Supply the working provider configuration path, never a plaintext key argument.')
    base=values.get('ANTHROPIC_BASE_URL') or 'https://api.deepseek.com/anthropic'
    if urlsplit(base).scheme not in {'https','http'}:
        raise ValueError('Invalid provider endpoint; no agent was started.')
    return {'ANTHROPIC_BASE_URL':base,'ANTHROPIC_API_KEY':key}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-agent-run',action='store_true')
    parser.add_argument('--provider-config',type=Path)
    parser.add_argument('--resume-capture',type=Path)
    parser.add_argument('--mode',choices=['bare','safe'],default='bare',help='safe retains built-in delegation; bare is the earlier minimal baseline')
    args=parser.parse_args()
    if not args.allow_agent_run:parser.error('Explicit user authorization required')
    try:provider=provider_environment(args.provider_config)
    except (ValueError,OSError) as error:parser.error(str(error))
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    destination=CAPTURES/(stamp+('-resume' if args.resume_capture else '-repair'))
    destination.mkdir(parents=True,exist_ok=False)
    if args.resume_capture:
        parent=args.resume_capture.resolve()
        if not parent.is_relative_to(CAPTURES.resolve()):parser.error('Resume must name one of this script’s isolated captures')
        metadata=json.loads((parent/'manifest.json').read_text())
        if metadata.get('profile')!='learn-search-v1' or not metadata.get('session_id'):parser.error('No resumable controlled session')
        workspace=Path(metadata['workspace']);config=Path(metadata['config_directory']);session_id=metadata['session_id']
        if not workspace.resolve().is_relative_to(CAPTURES.resolve()) or not config.resolve().is_relative_to(CAPTURES.resolve()):parser.error('Invalid controlled session paths')
        prompt='Continue the previous repair session. Do not modify files or start agents. Explain which search behaviors you fixed and which limitations remain; distinguish tests from assumptions. Run node --test search.test.mjs once more. Work only in this controlled directory; do not inspect any other directory, configuration, environment or private sessions.'
        tools='Read,Bash';allowed='Read,Bash(node --test search.test.mjs)'
        session_flags=['--resume',session_id]
    else:
        workspace=destination/'workspace';shutil.copytree(ROOT/'research/learn-search',workspace)
        execute(['git','init','-q'],workspace);execute(['git','add','.'],workspace)
        config=destination/'cli-config';session_id=str(uuid.uuid4())
        prompt='Work only in this controlled directory. Read TRACE_RULES.md, search.mjs and search.test.mjs. Run node --test search.test.mjs before editing. Use the reviewer subagent exactly once to inspect these files read-only for likely bugs; tell it not to spawn agents. Then fix only search.mjs according to the tests; do not modify tests or rules. Run node --test search.test.mjs after the edit. No other directories, configuration, private sessions, environment inspection, network tools, installs, commits or pushes. Describe actual results and limitations.'
        tools='Read,Edit,Bash,Agent';allowed='Read,Edit,Bash(node --test search.test.mjs),Agent'
        session_flags=['--session-id',session_id]
    if args.mode=='safe' and not args.resume_capture:
        prompt=prompt.replace('Use the reviewer subagent exactly once to inspect these files read-only for likely bugs; tell it not to spawn agents.', 'Use the Agent tool exactly once with the built-in Explore subagent to inspect search.mjs and search.test.mjs read-only for likely bugs. Tell it to use Read only, never shell commands, modifications, other directories or additional agents. Wait for its result before editing.')
    tests_before=(workspace/'search.test.mjs').read_bytes()
    before=execute(['node','--test','search.test.mjs'],workspace)
    env=os.environ.copy();env.update(provider)
    env.update({'CLAUDE_CONFIG_DIR':str(config),'ANTHROPIC_MODEL':'deepseek-flash','CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC':'1','DISABLE_TELEMETRY':'1','DISABLE_ERROR_REPORTING':'1'})
    for family in ['OPUS','SONNET','HAIKU']:env['ANTHROPIC_DEFAULT_'+family+'_MODEL']='deepseek-flash'
    reviewer={'reviewer':{'description':'Read-only review of the controlled search fixture','prompt':'Read search.mjs and search.test.mjs in the current directory. Identify likely bugs. Never modify files, run commands, inspect other paths or start another agent.','tools':['Read'],'model':'inherit'}}
    command=['claude','--safe-mode' if args.mode=='safe' else '--bare','-p',prompt,'--model','deepseek-flash','--output-format','stream-json','--verbose','--strict-mcp-config','--mcp-config','{"mcpServers":{}}','--tools',tools,'--allowedTools',allowed,'--permission-mode','acceptEdits','--max-turns','12','--max-budget-usd','1',*session_flags]
    if not args.resume_capture and args.mode=='bare':command+=['--agents',json.dumps(reviewer)]
    version=execute(['claude','--version'],workspace)
    result=execute(command,workspace,timeout=240,env=env)
    after=execute(['node','--test','search.test.mjs'],workspace)
    diff=execute(['git','diff','--','search.mjs','search.test.mjs'],workspace)
    metadata={'profile':'learn-search-v1','session_id':session_id,'workspace':str(workspace),'config_directory':str(config),'captured_at':stamp,'model':'deepseek-flash','provider_host':urlsplit(provider['ANTHROPIC_BASE_URL']).hostname,'cli_version':version['stdout'].strip(),'exit_code':result['exit_code'],'timed_out':result['timed_out'],'tests_unchanged':tests_before==(workspace/'search.test.mjs').read_bytes(),'resume':bool(args.resume_capture),'cli_mode':args.mode,'trace_sha256':hashlib.sha256(result['stdout'].encode()).hexdigest()}
    for name,value in [('manifest.json',metadata),('before-tests.json',before),('after-tests.json',after),('diff.json',diff)]:write_json_atomic(destination/name,value)
    write_text_atomic(destination/'trace.jsonl',result['stdout']);write_text_atomic(destination/'stderr.txt',result['stderr'])
    print(json.dumps({'capture_directory':str(destination),'exit_code':result['exit_code'],'timed_out':result['timed_out'],'tests_unchanged':metadata['tests_unchanged'],'before_tests_exit':before['exit_code'],'after_tests_exit':after['exit_code']}))


if __name__=='__main__':main()
