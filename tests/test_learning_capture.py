"""Capture preflight must not start an agent when provider configuration is absent."""
import json
import sys
import pytest
from app.storage import write_json_atomic, write_text_atomic
from scripts import capture_learning_run as capture


def clear_provider(monkeypatch):
    for name in capture.PROVIDER_KEYS:monkeypatch.delenv(name,raising=False)


def test_missing_credentials_prevents_any_process_start(monkeypatch):
    clear_provider(monkeypatch)
    called=[]
    monkeypatch.setattr(capture,'execute',lambda *args,**kwargs:called.append(args))
    monkeypatch.setattr(sys,'argv',['capture_learning_run.py','--allow-agent-run'])
    with pytest.raises(SystemExit) as error:capture.main()
    assert error.value.code==2
    assert called==[]


def test_explicit_provider_config_passes_only_credentials_and_endpoint(tmp_path,monkeypatch):
    clear_provider(monkeypatch)
    path=tmp_path/'settings.json'
    write_json_atomic(path,{'env':{'ANTHROPIC_AUTH_TOKEN':'fake-test-only','ANTHROPIC_BASE_URL':'https://api.deepseek.com/anthropic','UNRELATED_SECRET':'must-not-copy'},'hooks':{'example':'never execute'}})
    result=capture.provider_environment(path)
    assert set(result)=={'ANTHROPIC_API_KEY','ANTHROPIC_BASE_URL'}
    assert result['ANTHROPIC_API_KEY']=='fake-test-only'


def test_deepseek_env_file_uses_official_endpoint_without_mutating_environment(tmp_path,monkeypatch):
    clear_provider(monkeypatch)
    path=tmp_path/'.env'
    write_text_atomic(path,'DEEPSEEK_API_KEY=fake-test-only\n')
    result=capture.provider_environment(path)
    assert result['ANTHROPIC_BASE_URL']=='https://api.deepseek.com/anthropic'
    assert 'ANTHROPIC_API_KEY' not in capture.os.environ
