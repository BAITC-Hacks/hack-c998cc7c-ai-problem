"""Local application / external text analysis boundary, without paid API calls."""
import json
import httpx
import pytest
from test_pipeline import client, store, segment
import config
import db
from llm_client import analyze, ProcessingError
from schemas import Metadata


def configure(monkeypatch, key='test-secret-key'):
    monkeypatch.setattr(config, 'LLM_HYBRID_URL', 'https://ai.example/v1')
    monkeypatch.setattr(config, 'LLM_HYBRID_MODEL', 'meeting-model')
    monkeypatch.setattr(config, 'LLM_API_KEY', key)


def test_api_health_exposes_readiness_without_secret(client, monkeypatch):
    configure(monkeypatch)
    health = client.get('/api/health')
    assert health.json()['hybrid_configured'] is True
    assert health.json()['hybrid_model'] == 'meeting-model'
    assert 'test-secret-key' not in health.text
    monkeypatch.setattr(config, 'LLM_API_KEY', '')
    assert client.get('/api/health').json()['hybrid_configured'] is False


def test_unconfigured_api_upload_is_rejected_before_creating_job(client, monkeypatch):
    configure(monkeypatch, '')
    response = client.post('/api/upload', files={'file': ('meeting.wav', b'bytes', 'audio/wav')},
        data={'metadata': json.dumps(dict(title='Meeting', meeting_at='2026-09-23T10:00:00', mode='HYBRID', hybrid_consent=True))})
    assert response.status_code == 503
    assert 'LLM_API_KEY_MISSING' in response.text
    assert db.list_meetings() == []


def test_api_analysis_sends_bearer_and_text_to_configured_provider(monkeypatch):
    configure(monkeypatch)
    calls = []
    def reply(self, url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps({'summary': ['Обсудили план.']})}}]}, request=httpx.Request('POST', url))
    monkeypatch.setattr(httpx.Client, 'post', reply)
    result = analyze([segment('Обсудили план.')], Metadata(title='Meeting', meeting_at='2026-09-23', mode='HYBRID', hybrid_consent=True))
    assert result.summary == ['Обсудили план.']
    url, kwargs = calls[0]
    assert url == 'https://ai.example/v1/chat/completions'
    assert kwargs['headers'] == {'Authorization': 'Bearer test-secret-key'}
    assert kwargs['json']['model'] == 'meeting-model'
    assert 'files' not in kwargs


def test_provider_error_has_actionable_code_without_response_secrets(monkeypatch):
    configure(monkeypatch)
    def reply(self, url, **kwargs):
        return httpx.Response(401, text='test-secret-key sensitive provider body', request=httpx.Request('POST', url))
    monkeypatch.setattr(httpx.Client, 'post', reply)
    with pytest.raises(ProcessingError, match='LLM_AUTH_FAILED') as error:
        analyze([segment('Обсудили план.')], Metadata(title='Meeting', meeting_at='2026-09-23', mode='HYBRID', hybrid_consent=True))
    assert 'test-secret-key' not in str(error.value)
