"""Isolated browser fixture. Never runs against the user's database."""
import os
from pathlib import Path
import sys
import tempfile
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='khattama-ui-')
os.environ['APP_AUTH_PASSWORD'] = ''
os.environ['PUBLIC_MODE'] = 'false'
os.environ['ALLOWED_HOSTS'] = 'localhost,127.0.0.1,testserver'
os.environ['DEFAULT_MODE'] = 'HYBRID'
os.environ['DEFAULT_ASR_MODE'] = 'API'
for key in ('ASR_API_URL', 'ASR_API_MODEL', 'ASR_API_KEY', 'LLM_HYBRID_URL', 'LLM_HYBRID_MODEL', 'LLM_API_KEY'):
    os.environ[key] = ''
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
uvicorn.run(main.app, host='127.0.0.1', port=8765, log_level='warning')
