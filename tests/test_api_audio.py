import io
import wave
import httpx
import pytest
from test_pipeline import client, store
import config
from schemas import Metadata
from llm_client import ProcessingError
from agents.transcribe_api import transcribe_api
import db
import orchestrator
import json


@pytest.fixture
def audio_api(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'ASR_API_URL', 'https://speech.example/v1')
    monkeypatch.setattr(config, 'ASR_API_MODEL', 'whisper-compatible')
    monkeypatch.setattr(config, 'ASR_API_KEY', 'audio-test-secret')
    monkeypatch.setattr(config, 'ASR_CHUNK_SECONDS', 2)
    path = tmp_path / 'input.wav'
    with wave.open(str(path), 'wb') as audio:
        audio.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        audio.writeframes(b'\0' * 16000 * 2 * 3)
    return path


def test_audio_transfer_requires_separate_consent():
    with pytest.raises(ValueError, match='audio transfer consent'):
        Metadata(title='a', meeting_at='2026-09-23', asr_mode='API')
    old = Metadata(title='a', meeting_at='2026-09-23')
    assert old.asr_mode == 'LOCAL'


def test_audio_chunks_preserve_global_times_and_unique_ids(audio_api, monkeypatch):
    calls = []
    def reply(self, url, **kwargs):
        assert url == 'https://speech.example/v1/audio/transcriptions'
        assert kwargs['headers']['Authorization'] == 'Bearer audio-test-secret'
        assert kwargs['data']['response_format'] == 'verbose_json'
        with wave.open(io.BytesIO(kwargs['files']['file'][1]), 'rb') as part:
            calls.append(part.getnframes() / part.getframerate())
        return httpx.Response(200, json={'segments': [{'start': 0, 'end': 1, 'text': 'Сәлем.'}]}, request=httpx.Request('POST', url))
    monkeypatch.setattr(httpx.Client, 'post', reply)
    result = transcribe_api(audio_api)
    assert calls == [2, 1]
    assert [(s.id, s.start, s.end) for s in result] == [('s0', 0, 1), ('s1', 2, 3)]


@pytest.mark.parametrize('body', [ {'text': 'No timestamps'}, {'segments': [{'start': -1, 'end': 1, 'text': 'a'}]}, {'segments': [{'start': 0, 'end': 30, 'text': 'a'}]}, {'segments': [], 'text': 'Omitted speech'} ])
def test_api_does_not_invent_missing_or_invalid_timestamps(audio_api, monkeypatch, body):
    monkeypatch.setattr(httpx.Client, 'post', lambda self, url, **kwargs: httpx.Response(200, json=body, request=httpx.Request('POST', url)))
    with pytest.raises(ProcessingError, match='ASR_INVALID_RESPONSE'):
        transcribe_api(audio_api)


def test_audio_provider_error_is_sanitized(audio_api, monkeypatch):
    monkeypatch.setattr(httpx.Client, 'post', lambda self, url, **kwargs: httpx.Response(401, text='audio-test-secret', request=httpx.Request('POST', url)))
    with pytest.raises(ProcessingError, match='ASR_AUTH_FAILED') as error:
        transcribe_api(audio_api)
    assert 'audio-test-secret' not in str(error.value)


def test_upload_worker_uses_both_apis_and_preserves_audio_times(client, audio_api, monkeypatch):
    monkeypatch.setattr(config, 'LLM_HYBRID_URL', 'https://text.example/v1')
    monkeypatch.setattr(config, 'LLM_HYBRID_MODEL', 'text-model')
    monkeypatch.setattr(config, 'LLM_API_KEY', 'text-test-secret')
    monkeypatch.setattr(orchestrator, 'transcribe_audio', lambda _: pytest.fail('API meeting must not use local ASR'))
    calls = []
    def reply(self, url, **kwargs):
        calls.append(url)
        if url.endswith('/audio/transcriptions'):
            body = {'segments': [{'start': 0, 'end': 1, 'text': 'Обсудили план.'}]}
        else:
            body = {'choices': [{'message': {'content': json.dumps({'summary': ['Обсудили план.']})}}]}
        return httpx.Response(200, json=body, request=httpx.Request('POST', url))
    meta = Metadata(title='API recording', meeting_at='2026-09-23', mode='HYBRID', hybrid_consent=True, asr_mode='API', audio_consent=True)
    response = client.post('/api/upload', files={'file': ('recording.wav', audio_api.read_bytes(), 'audio/wav')}, data={'metadata': meta.model_dump_json()})
    assert response.status_code == 202
    monkeypatch.setattr(httpx.Client, 'post', reply)
    orchestrator.process(db.claim())
    meeting = db.get_meeting(response.json()['meeting_id'])
    assert meeting['status'] == 'done', meeting['error']
    assert [s['start'] for s in meeting['draft']['transcript']] == [0, 2]
    assert meeting['draft']['summary'] == ['Обсудили план.']
    assert calls == ['https://speech.example/v1/audio/transcriptions'] * 2 + ['https://text.example/v1/chat/completions']
