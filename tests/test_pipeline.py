"""Text fixtures test extraction contracts, not speech recognition."""
import io
import json
import sys
from pathlib import Path
from datetime import date
from concurrent.futures import ThreadPoolExecutor
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import config
import db
from sqlalchemy import create_engine
from fastapi.testclient import TestClient
from schemas import Segment, Draft, Metadata, Analysis, Assignment, validate_evidence
from agents.extract import extract_rules
from agents.export import build_docx,build_pdf
from date_parser import normalize_deadline
from llm_client import endpoint,ProcessingError,chunks,analyze
import orchestrator
import main

REF=date(2026,9,23)
def segment(text,id='s1',start=0,speaker=None):
    return Segment(id=id,text=text,start=start,end=start+5,speaker=speaker)
def metadata(**kw):
    return Metadata(title='Жоба Ә Ғ Қ Ң Ө Ұ Ү Һ І',meeting_at='2026-09-23T10:00:00',mode='RULES',**kw).model_dump(mode='json')
def fixture_draft():
    segments=[segment('Айдана, подготовь смету жұмаға дейін. Жоқ, дүйсенбіге ауыстырайық.')]
    a=extract_rules(segments,REF)
    return Draft(**a.model_dump(),transcript=segments).model_dump(mode='json')

@pytest.fixture
def store(tmp_path,monkeypatch):
    engine=create_engine('sqlite:///'+str(tmp_path/'test.db'),connect_args={'check_same_thread':False})
    monkeypatch.setattr(db,'engine',engine)
    monkeypatch.setattr(config,'UPLOAD_DIR',tmp_path)
    monkeypatch.setattr(config,'DATA_DIR',tmp_path)
    db.init_db()
    yield tmp_path
    engine.dispose()
@pytest.fixture
def client(store,monkeypatch):
    monkeypatch.setattr(orchestrator,'start',lambda:False)
    with TestClient(main.app) as c:
        yield c

def create_ready(store):
    mid=db.create_meeting('audio.wav',store/'audio.wav',metadata())
    db.finish(mid,fixture_draft())
    return mid

@pytest.mark.parametrize('raw,expected',[
 ('к пятнице','2026-09-25'),('дүйсенбіге дейін','2026-09-28'),('жұмаға дейін','2026-09-25'),
 ('через два дня','2026-09-25'),('екі күннен кейін','2026-09-25'),('ертең','2026-09-24'),
 ('2026-10-02','2026-10-02'),('до 25.09.2026','2026-09-25'),
 ('до конца недели',None),('келесі аптада',None),('к среде',None),('до 31.02.2026',None),('',None)])
def test_dates(raw,expected):
    assert normalize_deadline(raw,REF)==expected

def test_mixed_change_is_one_assignment():
    d=fixture_draft()
    assert len(d['assignments'])==1
    a=d['assignments'][0]
    assert a['owner']=='Айдана'
    assert a['deadline']=='2026-09-28'
    assert len(a['evidence'])==2
    validate_evidence(Analysis.model_validate({k:v for k,v in d.items() if k not in ('transcript','reviewed')}),[Segment.model_validate(x) for x in d['transcript']])

def test_kazakh_and_speaker_not_owner():
    a=extract_rules([segment('Айдана, есепті ертең дайындаңыз.',speaker='Марат')],REF).assignments[0]
    assert a.owner=='Айдана' and str(a.deadline)=='2026-09-24'

def test_proposal_not_task():
    r=extract_rules([segment('Предлагаю подготовить отчёт к пятнице.')],REF)
    assert not r.assignments and r.decisions[0].kind=='proposal'

def test_cancel_and_cross_segment_correction():
    r=extract_rules([segment('Айдана, подготовь смету к пятнице.'),segment('Нет, перенесём на понедельник.','s2',5),segment('Отменяем это поручение.','s3',10)],REF)
    assert len(r.assignments)==1
    assert r.assignments[0].status=='cancelled'
    assert str(r.assignments[0].deadline)=='2026-09-28'
    assert len(r.assignments[0].evidence)==3

def test_unclear_owner_and_period():
    a=extract_rules([segment('Необходимо направить письмо до конца недели.')],REF).assignments[0]
    assert a.owner is None and a.deadline is None
    assert a.deadline_raw=='до конца недели'

def test_unrelated_cancellation_is_not_guessed():
    r=extract_rules([segment('Айдана, подготовь смету.'),segment('Далее обсуждаем бюджет.','s2'),segment('Отменяем решение.','s3')],REF)
    assert r.assignments[0].status=='open' and r.questions

def test_evidence_rejects_fabrication():
    d=Draft.model_validate(fixture_draft())
    d.assignments[0].evidence[0].quote='invented'
    with pytest.raises(ValueError):validate_evidence(d,d.transcript)

def test_local_disallows_outbound_and_proxy(monkeypatch):
    monkeypatch.setattr(config,'LLM_LOCAL_URL','https://api.example.com/v1')
    with pytest.raises(ProcessingError,match='LOCAL_ENDPOINT'):endpoint('LOCAL')
    with pytest.raises(ValueError):Metadata(title='a',meeting_at='2026-09-23',mode='HYBRID')

def test_missing_model(monkeypatch,tmp_path):
    from agents.transcribe import transcribe_audio
    monkeypatch.setattr(config,'WHISPER_MODEL',str(tmp_path/'missing'))
    with pytest.raises(ProcessingError,match='ASR_MODEL_MISSING'):transcribe_audio('anything')

def test_all_long_recording_segments_are_chunked():
    ss=[segment('Сөз '*1000,id=f's{i}') for i in range(30)]
    batches=list(chunks(ss))
    assert len(batches)>1
    assert [s.id for b in batches for s in b]==[s.id for s in ss]

def test_llm_unavailable_no_fallback(monkeypatch):
    import httpx
    monkeypatch.setattr(config,'LLM_LOCAL_URL','http://127.0.0.1:1/v1')
    with pytest.raises(ProcessingError,match='LLM_UNAVAILABLE'):
        analyze([segment('Поручаю подготовить отчёт.')],Metadata(title='a',meeting_at='2026-09-23'))

def test_atomic_claim_and_recovery(store):
    mid=db.create_meeting('a.wav',store/'a.wav',metadata())
    with ThreadPoolExecutor(max_workers=4) as pool:
        claims=list(pool.map(lambda _:db.claim(),range(4)))
    assert sum(x is not None for x in claims)==1
    db.stage(mid,'analyze',[segment('test').model_dump()])
    db.recover()
    m=db.claim()
    assert m['id']==mid and m['checkpoint'][0]['text']=='test'

def test_immutable_approval_and_stale_revision(store):
    mid=create_ready(store);m=db.get_meeting(mid);d=m['draft']
    with pytest.raises(ValueError):db.approve(mid,m['revision'])
    d['reviewed']=True
    for a in d['assignments']:
        a['review']='confirmed';a['unspecified']=['expected_result']
    db.save_draft(mid,m['revision'],d)
    m=db.get_meeting(mid);vid=db.approve(mid,m['revision'])
    assert db.approve(mid,m['revision'])==vid
    original=db.version(mid,vid)
    d['summary']=['Changed']
    db.save_draft(mid,m['revision'],d)
    assert db.version(mid,vid)==original
    with pytest.raises(ValueError):db.save_draft(mid,m['revision'],d)

def test_source_change_invalidates_review(store):
    mid=create_ready(store);m=db.get_meeting(mid);d=m['draft']
    d['reviewed']=True;d['assignments'][0]['review']='confirmed'
    d['transcript'][0]['text']='Новая реплика'
    db.save_draft(mid,m['revision'],d)
    d=db.get_meeting(mid)['draft']
    assert not d['reviewed'] and d['assignments'][0]['review']=='needs_review'
    with pytest.raises(ValueError):db.approve(mid,m['revision']+1)

def test_reanalysis_preserves_manual_changes(store):
    mid=create_ready(store);m=db.get_meeting(mid)
    m['draft']['summary']=['Manual summary']
    db.save_draft(mid,m['revision'],m['draft'])
    m=db.get_meeting(mid)
    db.enqueue(mid,m['revision'],True)
    with pytest.raises(ValueError):db.enqueue(mid,m['revision'],True)
    db.finish(mid,fixture_draft(),True)
    m=db.get_meeting(mid)
    assert m['draft']['summary']==['Manual summary'] and m['candidate']
    db.apply_candidate(mid,m['revision'])
    assert db.get_meeting(mid)['candidate'] is None

def test_upload_validation_and_origin(client,monkeypatch):
    assert client.post('/api/upload',files={'file':('test.exe',b'abc')},data={'metadata':json.dumps(metadata())}).status_code==415
    assert client.post('/api/upload',files={'file':('test.wav',b'abc')},data={'metadata':'{}'}).status_code==422
    monkeypatch.setattr(config,'MAX_UPLOAD_BYTES',2)
    assert client.post('/api/upload',files={'file':('test.wav',b'abc')},data={'metadata':json.dumps(metadata())}).status_code==413
    assert client.post('/api/upload',headers={'Origin':'https://evil.example'}).status_code==403

def test_history_range_and_export(client,store):
    mid=create_ready(store)
    (store/'audio.decoded.wav').write_bytes(bytes(range(256)))
    r=client.get(f'/api/meetings/{mid}/audio',headers={'Range':'bytes=10-19'})
    assert r.status_code==206 and r.content==bytes(range(10,20))
    assert 'path' not in client.get(f'/api/meetings/{mid}').json()
    assert client.get(f'/api/meetings/{mid}/export?format=pdf').content.startswith(b'%PDF')
    assert client.get(f'/api/meetings/{mid}/versions/999').status_code==404
    assert client.get(f'/api/meetings/{mid}/audit').json()

def test_no_speech_is_error_not_fake_result(store,monkeypatch):
    mid=db.create_meeting('silence.wav',store/'silence.wav',metadata())
    monkeypatch.setattr(orchestrator,'decode',lambda *a:None)
    monkeypatch.setattr(orchestrator,'transcribe_audio',lambda _:[])
    orchestrator.process(db.claim())
    m=db.get_meeting(mid)
    assert m['status']=='error' and m['error'].startswith('NO_SPEECH')
    assert not m['draft']['transcript']

def test_register_overdue_closed_and_no_deadline(client,store):
    mid=create_ready(store);m=db.get_meeting(mid)
    a=m['draft']['assignments'][0];a['deadline']='2020-01-01';a['status']='done'
    db.save_draft(mid,m['revision'],m['draft'])
    assert not client.get('/api/assignments').json()['assignments'][0]['overdue']
    m=db.get_meeting(mid);a=m['draft']['assignments'][0];a['deadline']=None;a['status']='open'
    db.save_draft(mid,m['revision'],m['draft'])
    assert not client.get('/api/assignments').json()['assignments'][0]['overdue']

def test_exports_kazakh_and_long_content(tmp_path):
    from docx import Document
    from pypdf import PdfReader
    snap=dict(metadata=metadata(),draft=fixture_draft(),revision=1)
    snap['draft']['summary']=['Ә Ғ Қ Ң Ө Ұ Ү Һ І <script> & '+('ұзақ мәтін '*80)]*12
    doc=build_docx(snap)
    assert 'Ә Ғ Қ Ң Ө Ұ Ү Һ І' in '\n'.join(p.text for p in Document(doc).paragraphs)
    pdf=build_pdf(snap)
    reader=PdfReader(pdf)
    assert len(reader.pages)>2
    text=''.join(p.extract_text() for p in reader.pages)
    assert 'Ә Ғ Қ Ң Ө Ұ Ү Һ І' in text and '<script>' in text
    assert 'ЧЕРНОВИК' in text
