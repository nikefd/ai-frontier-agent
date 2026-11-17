"""Run one explicitly authorized, isolated read-only Skill exercise with HTTP capture."""
import argparse
import json
import os
import shutil
import uuid
from pathlib import Path
from datetime import datetime,timezone
from scripts.capture_learning_run import ROOT,CAPTURES,provider_environment
from scripts.capture_runtime_case import execute
from scripts.learning_http_capture import LearningHttpCapture
from app.storage import write_json_atomic,write_text_atomic


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-agent-run',action='store_true')
    parser.add_argument('--provider-config',type=Path,required=True)
    args=parser.parse_args()
    if not args.allow_agent_run:parser.error('Explicit user authorization required')
    provider=provider_environment(args.provider_config)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');destination=CAPTURES/(stamp+'-skill')
    workspace=destination/'workspace';shutil.copytree(ROOT/'research/learn-search',workspace)
    config=destination/'cli-config';plugin=destination/'exercise-plugin'
    write_json_atomic(plugin/'.claude-plugin/plugin.json',{'name':'search-check','version':'1.0.0','description':'Original isolated learning fixture'})
    skill='''---
name: verify-search
description: Read-only verification of the isolated article search exercise.
---
Read TRACE_RULES.md, search.mjs and search.test.mjs in the current exercise directory only.
Run node --test search.test.mjs exactly once. Report passes, failures and evidence.
Do not edit files, read other directories, inspect environment/settings, start agents, install packages or use network tools.
A failed test is an observed finding, not permission to fix code.
'''
    write_text_atomic(plugin/'skills/verify-search/SKILL.md',skill)
    env=os.environ.copy();env.update(provider)
    env.update(CLAUDE_CONFIG_DIR=str(config),ANTHROPIC_MODEL='deepseek-flash',CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1',DISABLE_TELEMETRY='1')
    for family in ['OPUS','SONNET','HAIKU']:env['ANTHROPIC_DEFAULT_'+family+'_MODEL']='deepseek-flash'
    prompt='Invoke the search-check:verify-search Skill exactly once for this isolated directory. Follow that Skill read-only, report the actual test results, and do not fix or modify anything. Never inspect other directories, configuration, environment or private sessions.'
    command=['claude','--setting-sources','','--settings','{"disableAllHooks":true}','--plugin-dir',str(plugin),'-p',prompt,'--model','deepseek-flash','--output-format','stream-json','--verbose','--strict-mcp-config','--mcp-config','{"mcpServers":{}}','--tools','Read,Bash,Skill','--allowedTools','Read,Bash(node --test search.test.mjs),Skill','--max-turns','8','--max-budget-usd','1','--session-id',str(uuid.uuid4())]
    before={p.name:p.read_bytes() for p in workspace.iterdir() if p.is_file()}
    with LearningHttpCapture(provider,destination/'http') as capture:
        env['ANTHROPIC_BASE_URL']=capture.base_url
        result=execute(command,workspace,timeout=240,env=env)
    unchanged=all((workspace/name).read_bytes()==data for name,data in before.items())
    write_text_atomic(destination/'trace.jsonl',result['stdout']);write_text_atomic(destination/'stderr.txt',result['stderr'])
    write_json_atomic(destination/'manifest.json',{'profile':'learn-skill-v1','captured_at':stamp,'workspace':str(workspace),'config_directory':str(config),'plugin_directory':str(plugin),'cli_version':execute(['claude','--version'],workspace)['stdout'].strip(),'exit_code':result['exit_code'],'timed_out':result['timed_out'],'files_unchanged':unchanged})
    print(json.dumps({'capture_directory':str(destination),'exit_code':result['exit_code'],'files_unchanged':unchanged}))
if __name__=='__main__':main()
