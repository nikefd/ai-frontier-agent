"""Trace fidelity and cancellation over the actual harness/client boundary."""
import io
import json
from threading import Event

from app.agent_runtime import AgentConfig, Harness, tool
from app.agent_runtime import llm
from app.agent_research import research_harness


def scripted_provider(monkeypatch, responses):
    requests = []
    monkeypatch.setitem(llm._CFG, 'api_key', 'test-only')
    def request(payload):
        requests.append(json.loads(json.dumps(payload)))
        return io.BytesIO(json.dumps({'choices':[{'message':responses.pop(0)}],
                                     'usage':{'prompt_tokens':23,'completion_tokens':5}}).encode())
    monkeypatch.setattr(llm, '_request', request)
    return requests


def intent():
    return {'role':'assistant','content':None,'tool_calls':[
        {'id':'call_1','type':'function','function':{'name':'lookup','arguments':'{"keyword":"Agent"}'}}]}


def test_trace_is_exact_sent_payload_and_tool_feedback(monkeypatch):
    @tool
    def lookup(keyword: str):
        return {'articles':[{'id':'a','title':keyword}], 'source':'articles.json'}
    requests = scripted_provider(monkeypatch,[intent(),{'role':'assistant','content':'Found Agent'}])
    events = list(Harness(AgentConfig(system_prompt='rules',tools=[lookup])).run(
        [{'role':'user','content':'find articles'}],trace=True))
    observed = [event['payload'] for event in events if event['type']=='model_request']
    assert observed == requests
    assert len(observed[0]['messages']) == 2  # later turns must not mutate earlier captures
    assert observed[1]['messages'][-1]['tool_call_id'] == 'call_1'
    result = next(event for event in events if event['type']=='tool_result')
    assert result['content'] == observed[1]['messages'][-1]['content']
    assert result['call_id'] == 'call_1'
    assert result['result']['articles'][0]['title'] == 'Agent'
    assert events[-1]['type']=='final'
    assert 'test-only' not in json.dumps(events)


def test_truncated_feedback_is_identical_to_next_request(monkeypatch):
    @tool
    def lookup(keyword: str):
        return {'text':'x'*1000}
    requests = scripted_provider(monkeypatch,[intent(),{'role':'assistant','content':'done'}])
    events=list(Harness(AgentConfig(system_prompt='rules',tools=[lookup],tool_result_max_chars=30)).run([],trace=True))
    result=next(e for e in events if e['type']=='tool_result')
    assert result['truncated'] is True
    assert len(result['result']['text'])==1000
    assert result['content']==requests[1]['messages'][-1]['content']


def test_stop_after_model_reply_does_not_execute_tool_or_next_model(monkeypatch):
    executed=[]
    @tool
    def lookup(keyword: str):
        executed.append(keyword)
        return {}
    requests=scripted_provider(monkeypatch,[intent()])
    cancelled=Event()
    iterator=Harness(AgentConfig(system_prompt='rules',tools=[lookup])).run([],trace=True,cancelled=cancelled)
    assert next(iterator)['type']=='model_request'
    assert next(iterator)['type']=='model_response'
    cancelled.set()
    assert list(iterator)==[{'type':'cancelled'}]
    assert not executed and len(requests)==1


def test_research_uses_only_existing_read_only_article_tools():
    harness=research_harness('test-research')
    assert set(harness.registry.names())=={'query_articles','read_article'}
    assert all(not tool.writes for tool in harness.config.tools)
    assert harness.config.max_tool_rounds==4
    assert harness.config.recall_provider is None


def test_endpoint_requires_identity_and_releases_admission(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app import agent_research as research
    from app.models import UserPublic
    app=FastAPI()
    app.include_router(research.router)
    client=TestClient(app)
    assert client.post('/api/agent/research',json={'message':'find Agent'}).status_code==401
    app.dependency_overrides[research.require_llm_quota]=lambda: UserPublic(id='research-test',email='test@example.org',email_verified=True)
    monkeypatch.setattr(research,'llm_configured',lambda:True)
    class StubHarness:
        def run(self,*args,**kwargs):
            yield {'type':'final','content':'done','citations':[]}
    monkeypatch.setattr(research,'research_harness',lambda uid:StubHarness())
    with client:
        response=client.post('/api/agent/research',json={'message':'find Agent'})
        assert response.status_code==200 and '"type": "final"' in response.text
        assert 'research-test' not in research._active
        research._active.add('research-test')
        try:
            assert client.post('/api/agent/research',json={'message':'duplicate'}).status_code==409
        finally:
            research._active.discard('research-test')
        assert client.post('/api/agent/research',json={'message':' '*3}).status_code==422
