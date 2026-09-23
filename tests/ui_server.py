"""Isolated browser fixture. Never runs against the user's database."""
import os
import json
from pathlib import Path
import secrets
import socket
import sys
import tempfile
import wave
from fastapi import HTTPException, Request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
# Never load a developer's credentials, data directory or provider overrides.
os.environ['PYTHON_DOTENV_DISABLED'] = 'true'
ready_file = os.environ.get('KHATTAMA_UI_READY_FILE')
temporary = tempfile.TemporaryDirectory(prefix='khattama-ui-', dir=Path(ready_file).parent if ready_file else None)
os.environ['DATA_DIR'] = temporary.name
os.environ['APP_AUTH_PASSWORD'] = ''
os.environ['PUBLIC_MODE'] = 'false'
os.environ['HOST'] = '127.0.0.1'
os.environ['ALLOWED_HOSTS'] = 'localhost,127.0.0.1,testserver'
os.environ['DEFAULT_MODE'] = 'HYBRID'
os.environ['DEFAULT_ASR_MODE'] = 'API'
for key in ('ASR_API_URL', 'ASR_API_MODEL', 'ASR_API_KEY', 'LLM_HYBRID_URL', 'LLM_HYBRID_MODEL', 'LLM_API_KEY', 'LLM_LOCAL_URL', 'LLM_LOCAL_MODEL', 'PDF_FONT'):
    os.environ[key] = ''
for key in ('FFMPEG', 'ASR_CHUNK_SECONDS', 'MAX_UPLOAD_MB', 'MAX_AUDIO_SECONDS', 'DIARIZATION_GAP_SECONDS'):
    os.environ.pop(key, None)
os.environ['WHISPER_MODEL'] = str(Path(temporary.name) / 'no-model')
# Bind before loading application data so a conflicting fixed port fails early.
listener = socket.socket()
listener.bind(('127.0.0.1', int(os.environ.get('KHATTAMA_UI_PORT', '8765'))))
listener.listen(128)
port = listener.getsockname()[1]
import db
from schemas import Metadata, Draft, Segment
from agents.extract import extract_rules
import main
import uvicorn

db.init_db()
meta = Metadata(title='Планирование запуска', meeting_at='2026-09-23T10:00:00', mode='RULES', participants=['Айдана', 'Тимур'])
path = Path(os.environ['DATA_DIR']) / 'uploads' / 'fixture.wav'
segments = [Segment(id='s1', start=0, end=5, speaker='Тимур', text='Айдана, подготовь смету к пятнице.'), Segment(id='s2', start=5, end=10, text='Решили запустить пилот в октябре.')]
draft = Draft(**extract_rules(segments, meta.meeting_at.date()).model_dump(), transcript=segments, reviewed=True)
for task in draft.assignments:
    task.review = 'confirmed'
    task.unspecified = ['expected_result']
mid = db.create_meeting('fixture.wav', path, meta.model_dump(mode='json'))
db.finish(mid, draft.model_dump(mode='json'))
with wave.open(str(path.with_suffix('.decoded.wav')), 'wb') as audio:
    audio.setnchannels(1)
    audio.setsampwidth(2)
    audio.setframerate(16000)
    audio.writeframes(b'\0' * 16000 * 2 * 12)
token = os.environ.get('KHATTAMA_UI_TOKEN') or secrets.token_urlsafe(24)


@main.app.get('/__test_ready__')
def fixture_identity():
    return {'token': token}


@main.app.post('/__test_shutdown__')
def stop_fixture(request: Request):
    if not secrets.compare_digest(request.headers.get('X-Test-Token', ''), token):
        raise HTTPException(403, 'Fixture token required')
    server.should_exit = True
    return {'status': 'stopping'}


if ready_file:
    Path(ready_file).write_text(json.dumps({'port': port, 'token': token}), encoding='utf-8')
try:
    server = uvicorn.Server(uvicorn.Config(main.app, host='127.0.0.1', port=port, log_level='warning'))
    server.run(sockets=[listener])
finally:
    listener.close()
    db.engine.dispose()
    temporary.cleanup()
