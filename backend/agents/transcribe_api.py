"""Timestamped ASR using an explicitly configured OpenAI-compatible API."""
import io
import math
import wave
from urllib.parse import urlsplit
import httpx
import config
from llm_client import ProcessingError
from schemas import Segment


def endpoint():
    try:
        parsed = urlsplit(config.ASR_API_URL)
        valid = parsed.scheme == 'https' and parsed.hostname and not any(
            (parsed.username, parsed.password, parsed.query, parsed.fragment))
    except ValueError:
        valid = False
    if not valid:
        raise ProcessingError('ASR_ENDPOINT_INVALID: configure HTTPS ASR_API_URL in backend/.env')
    if not config.ASR_API_MODEL:
        raise ProcessingError('ASR_MODEL_MISSING: configure ASR_API_MODEL in backend/.env')
    if not config.ASR_API_KEY:
        raise ProcessingError('ASR_API_KEY_MISSING: configure ASR_API_KEY in backend/.env')
    return config.ASR_API_URL.rstrip('/') + '/audio/transcriptions'


def transcribe_api(path, progress=lambda stage: None):
    url = endpoint()
    segments = []
    with wave.open(str(path), 'rb') as source, httpx.Client(
        timeout=httpx.Timeout(180, connect=15), follow_redirects=False, trust_env=False
    ) as client:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 16000):
            raise ProcessingError('ASR_AUDIO_FORMAT: expected normalized 16 kHz mono PCM WAV')
        chunk_frames = min(max(config.ASR_CHUNK_SECONDS, 1), 600) * 16000
        total = math.ceil(source.getnframes() / chunk_frames)
        for index in range(total):
            offset = source.tell() / 16000
            frames = source.readframes(chunk_frames)
            duration = len(frames) / 32000
            content = io.BytesIO()
            with wave.open(content, 'wb') as output:
                output.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
                output.writeframes(frames)
            progress(f'transcribe_chunk_{index + 1}_of_{total}')
            try:
                response = client.post(url,
                    headers={'Authorization': 'Bearer ' + config.ASR_API_KEY},
                    data={'model': config.ASR_API_MODEL, 'response_format': 'verbose_json',
                          'timestamp_granularities[]': 'segment'},
                    files={'file': ('audio.wav', content.getvalue(), 'audio/wav')})
                response.raise_for_status()
                payload = response.json()
                entries = payload['segments']
                if not isinstance(entries, list) or (not entries and payload.get('text', '').strip()):
                    raise ValueError('Timestamped segments required')
                for entry in entries:
                    start, end = float(entry['start']), float(entry['end'])
                    text = entry['text'].strip()
                    if not (math.isfinite(start) and math.isfinite(end) and 0 <= start <= end <= duration + 0.1):
                        raise ValueError('Invalid segment time')
                    if text:
                        segments.append(Segment(id=f's{len(segments)}', start=offset + min(start, duration),
                                                end=offset + min(end, duration), text=text))
            except httpx.HTTPStatusError as error:
                code = error.response.status_code
                if code in (401, 403):
                    raise ProcessingError('ASR_AUTH_FAILED: check ASR_API_KEY and model access') from None
                if code == 429:
                    raise ProcessingError('ASR_RATE_LIMIT: check provider quota or retry later') from None
                raise ProcessingError(f'ASR_HTTP_ERROR: provider returned HTTP {code}; check model and verbose_json support') from None
            except httpx.HTTPError:
                raise ProcessingError('ASR_UNAVAILABLE: provider did not respond; retry later') from None
            except (ValueError, KeyError, TypeError, AttributeError):
                raise ProcessingError('ASR_INVALID_RESPONSE: provider must return verbose_json with valid timestamped segments') from None
    return segments
