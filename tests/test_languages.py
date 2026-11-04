import asyncio
import json
from xml.etree import ElementTree as ET

import pytest

from app.briefing_languages import parse_bilingual_briefing, select_briefing
from app.locale import current_language, localized_messages, output_language
from app.llm_client import LLMUnavailable
from app.routers.rss import build_digest_rss


def test_bilingual_briefing_validation_preserves_both_bodies_and_citations():
    value = {'body': '## 今日重点\n中文 [1]', 'body_en': '## Top stories\nEnglish [1]'}
    assert parse_bilingual_briefing('```json\n' + json.dumps(value) + '\n```') == value
    assert select_briefing(value, 'en')['body'] == value['body_en']
    assert value['body'].startswith('## 今日重点')
    assert select_briefing({'body':'old Chinese'}, 'en')['body'] == ''
    with pytest.raises(LLMUnavailable):
        parse_bilingual_briefing('{"body":"Chinese only"}')
    with pytest.raises(LLMUnavailable):
        parse_bilingual_briefing('not JSON')
    with pytest.raises(LLMUnavailable):
        parse_bilingual_briefing('{"body":"Chinese [1]","body_en":"English [2]"}')


@pytest.mark.asyncio
async def test_language_is_task_local_and_messages_are_not_mutated():
    messages = [{'role':'system','content':'Write Chinese JSON.'}, {'role':'user','content':'input'}]
    async def worker(language):
        with output_language(language):
            await asyncio.sleep(0)
            return current_language(), localized_messages(messages)
    en, zh = await asyncio.gather(worker('en'),worker('zh'))
    assert 'English' in en[1][0]['content']
    assert zh[1] == messages
    assert messages[0]['content'] == 'Write Chinese JSON.'
    assert current_language() == 'zh'


def test_english_rss_never_substitutes_a_chinese_only_briefing():
    sample={'date':'2026-11-04','generated_at':'2026-11-04T00:00:00+00:00','body':'中文 [1]',
            'body_en':'English [1]','cohort':[{'url':'https://example.test/release'}]}
    english=ET.fromstring(build_digest_rss([sample, {**sample,'body_en':''}], 'https://site.test', 'en'))
    assert english.findtext('channel/language') == 'en'
    items=english.findall('channel/item')
    assert len(items)==1
    assert 'English' in items[0].findtext('description')
    assert 'https://example.test/release' in items[0].findtext('description')
    assert items[0].findtext('link').endswith('?lang=en')
    chinese=ET.fromstring(build_digest_rss([sample],'https://site.test'))
    assert chinese.findtext('channel/language')=='zh-CN'
    assert '中文' in chinese.findtext('channel/item/description')


def test_english_source_status_does_not_change_classification():
    from app.source_freshness import classify_content_freshness
    from app.routers.ai_news import _source_health
    with output_language('en'):
        content = classify_content_freshness(None, {'cadence':'fast'})
        health = _source_health({'last_error':'failure', 'consecutive_failures':2})
    assert content['content_status'] == 'unknown'
    assert content['content_reason'] == 'No trustworthy source publication date yet'
    assert health['health_status'] == 'error'
    assert 'consecutive failures: 2' in health['health_reason']


def test_public_language_reads_select_cache_without_writing(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app.routers.ai_news as news
    from app.main import app
    cache=tmp_path/'summary.json'
    cache.write_text(json.dumps({'body':'中文 [1]', 'body_en':'English [1]'}))
    before=cache.read_bytes()
    monkeypatch.setattr(news,'SUMMARY_FILE',cache)
    monkeypatch.setattr(news,'_articles_for_today',lambda:[])
    monkeypatch.setattr(news,'_load_articles',lambda:[])
    monkeypatch.setattr(news,'_load_sources_meta',lambda:{})
    monkeypatch.setattr(news,'DEFAULT_FEED_SPECS',[{'url':'https://example.test/feed','name':'Fixture'}])
    client=TestClient(app)
    assert client.get('/api/ai-news/summary/today?lang=en').json()['summary']['body']=='English [1]'
    assert client.get('/api/ai-news/summary/today').json()['summary']['body']=='中文 [1]'
    assert client.get('/api/ai-news/summary/today?lang=unsupported').status_code==422
    assert client.get('/api/ai-news/sources',headers={'accept-language':'en-US,en;q=0.9'}).json()[0]['health_reason']=='First fetch has not completed'
    assert client.get('/api/ai-news/sources',headers={'accept-language':'zh'}).json()[0]['health_reason']=='尚未完成首次抓取'
    assert cache.read_bytes()==before
