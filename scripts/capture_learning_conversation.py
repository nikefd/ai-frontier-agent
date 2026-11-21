"""Capture three normal user turns in one new, isolated Claude Code session."""
import argparse
import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime,timezone
from pathlib import Path
from scripts.capture_learning_run import CAPTURES,ROOT,provider_environment
from scripts.capture_runtime_case import execute
from scripts.learning_http_capture import LearningHttpCapture
from app.storage import write_json_atomic,write_text_atomic

PROMPTS=[
 '请读取articles.json，给我选4篇适合开始了解Agent工程的入门文章，按建议阅读顺序整理成shortlist.md。用Markdown表格，第一列保留原始ID，并列出标题、预计阅读分钟和一句选择理由。只能使用这个目录中的原创教学条目，不要编造新文章、联网或读取其他目录。',
 '我想收窄一下：这次只看评估和记忆，暂时不看工具基础、微调或部署；每篇不超过20分钟。请基于刚才的清单更新shortlist.md，继续保留ID和阅读时间，并在回复中说明删改了什么。不要修改articles.json。',
 '好，把筛完的3篇安排成3天的阅读计划，写到reading-plan.md。用一个Markdown表格，列为Day、ID、标题、阅读分钟、可选小练习、验收点；天数用Day 1、Day 2、Day 3。每天阅读最多20分钟，小练习不计入阅读时间。沿用前面评估和记忆的偏好，不要重新加入已排除的文章；回复说明最终安排。',
]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-agent-run',action='store_true')
    parser.add_argument('--provider-config',type=Path,required=True)
    args=parser.parse_args()
    if not args.allow_agent_run:parser.error('Explicit user authorization required')
    try:provider=provider_environment(args.provider_config)
    except (ValueError,OSError) as error:parser.error(str(error))
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');destination=CAPTURES/(stamp+'-conversation')
    workspace=destination/'workspace';shutil.copytree(ROOT/'research/learn-reading',workspace)
    execute(['git','init','-q'],workspace)
    config=destination/'cli-config';session=str(uuid.uuid4())
    source=(workspace/'articles.json').read_bytes();turns=[]
    env=os.environ.copy();env.update(provider)
    env.update(CLAUDE_CONFIG_DIR=str(config),ANTHROPIC_MODEL='deepseek-flash',CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1',DISABLE_TELEMETRY='1')
    for family in ['OPUS','SONNET','HAIKU']:env['ANTHROPIC_DEFAULT_'+family+'_MODEL']='deepseek-flash'
    for number,prompt in enumerate(PROMPTS,1):
        turn_dir=destination/f'turn-{number}';turn_dir.mkdir()
        command=['claude','--safe-mode','-p',prompt,'--model','deepseek-flash','--output-format','stream-json','--verbose','--strict-mcp-config','--mcp-config','{"mcpServers":{}}','--tools','Read,Write,Edit','--allowedTools','Read,Write,Edit','--permission-mode','acceptEdits','--max-turns','8','--max-budget-usd','1',*(['--session-id',session] if number==1 else ['--resume',session])]
        with LearningHttpCapture(provider,turn_dir/'http') as capture:
            env['ANTHROPIC_BASE_URL']=capture.base_url
            result=execute(command,workspace,timeout=240,env=env)
        write_text_atomic(turn_dir/'trace.jsonl',result['stdout']);write_text_atomic(turn_dir/'stderr.txt',result['stderr'])
        files={name:(workspace/name).read_text() for name in ('shortlist.md','reading-plan.md') if (workspace/name).exists()}
        write_json_atomic(turn_dir/'files.json',files)
        record={'user_turn':number,'prompt':prompt,'exit_code':result['exit_code'],'timed_out':result['timed_out'],'http_directory':str(turn_dir/'http'),'source_unchanged':source==(workspace/'articles.json').read_bytes()}
        turns.append(record);print(json.dumps({'user_turn':number,'exit_code':result['exit_code'],'source_unchanged':record['source_unchanged']}),flush=True)
        if result['exit_code'] or result['timed_out']:break
    write_json_atomic(destination/'manifest.json',{'profile':'learn-conversation-v1','captured_at':stamp,'session_id':session,'workspace':str(workspace),'config_directory':str(config),'cli_version':execute(['claude','--version'],workspace)['stdout'].strip(),'turns':turns,'source_sha256':hashlib.sha256(source).hexdigest()})
    print(json.dumps({'capture_directory':str(destination),'completed_user_turns':len(turns)}))
if __name__=='__main__':main()
