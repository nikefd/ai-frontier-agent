import json
import httpx
from scripts import learning_http_capture as wire


def test_bridge_captures_bodies_not_credentials_and_rejects_other_paths(tmp_path,monkeypatch):
    real_client=httpx.Client
    def upstream(request):
        assert request.url.host=='api.deepseek.com'
        assert request.headers['x-api-key']=='test-secret-never-record'
        return httpx.Response(200,headers={'content-type':'text/event-stream'},content=b'event: message_stop\ndata: {"type":"message_stop"}\n\n')
    monkeypatch.setattr(wire.httpx,'Client',lambda **kwargs:real_client(transport=httpx.MockTransport(upstream)))
    with wire.LearningHttpCapture({'ANTHROPIC_BASE_URL':'https://api.deepseek.com/anthropic','ANTHROPIC_API_KEY':'test-secret-never-record'},tmp_path) as bridge:
        with real_client(trust_env=False) as client:
            response=client.post(bridge.base_url+'/v1/messages',json={'model':'test','system':'own fixture','messages':[]})
            assert response.status_code==200
            assert client.post(bridge.base_url+'/other',json={}).status_code==404
    files=list(tmp_path.glob('*.json'));assert len(files)==1
    text=files[0].read_text();record=json.loads(text)
    assert 'test-secret-never-record' not in text
    assert 'headers' not in record
    assert record['request']['system']=='own fixture'
    assert record['response'].startswith('event: message_stop')
    assert record['complete'] is True
