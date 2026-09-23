"""Local meeting review application."""
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import ValidationError
import config
import db
import orchestrator
from schemas import Draft, Metadata, Strict, validate_evidence
from agents.export import build_docx, build_pdf

@asynccontextmanager
async def lifespan(app):
    db.init_db()
    owned = orchestrator.start()
    yield
    if owned:
        orchestrator.stop()

app = FastAPI(title='Хаттама AI',version='0.2.0',lifespan=lifespan)
from request_limit import RequestLimit
app.add_middleware(RequestLimit)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['localhost','127.0.0.1','[::1]','testserver'])

@app.middleware('http')
async def local_origin(request: Request, call_next):
    origin = request.headers.get('origin')
    if request.method not in ('GET','HEAD','OPTIONS') and origin:
        if urlsplit(origin).netloc != request.headers.get('host'):
            return JSONResponse({'detail':'Cross-origin writes are disabled'},403)
    if request.headers.get('sec-fetch-site') == 'cross-site':
        return JSONResponse({'detail':'Cross-site access is disabled'},403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; media-src 'self' blob:; img-src 'self' data:; frame-ancestors 'none'"
    return response

class WriteDraft(Strict):
    revision: int
    draft: Draft
class Revision(Strict):
    revision: int

def required(mid):
    m = db.get_meeting(mid)
    if not m:
        raise HTTPException(404,'Meeting not found')
    return m

def mutate(fn,*args):
    try:
        return fn(*args)
    except LookupError as e:
        raise HTTPException(404,str(e)) from None
    except ValueError as e:
        raise HTTPException(409,str(e)) from None

@app.get('/api/health')
def health():
    from shutil import which
    return dict(status='ok',default_mode='LOCAL',model_available=(Path(config.WHISPER_MODEL)/'model.bin').is_file(),
                ffmpeg_available=bool(which(config.FFMPEG)),diarization='manual',
                hybrid_endpoint=urlsplit(config.LLM_HYBRID_URL).hostname,
                local_endpoint=config.LLM_LOCAL_URL,max_upload_mb=config.MAX_UPLOAD_BYTES//1024//1024)

@app.post('/api/upload',status_code=202)
def upload(file: UploadFile = File(...), metadata: str = Form(...)):
    try:
        meta = Metadata.model_validate_json(metadata)
    except (ValidationError,ValueError):
        raise HTTPException(422,'Invalid metadata: title, meeting date/time, IANA timezone and explicit HYBRID consent are required') from None
    ext = Path(file.filename or '').suffix.lower()
    if ext not in config.ALLOWED_EXT:
        raise HTTPException(415,'Supported formats: WAV, MP3, MP4')
    path = config.UPLOAD_DIR / (uuid4().hex + ext)
    size = 0
    try:
        with path.open('wb') as out:
            while chunk := file.file.read(1024*1024):
                size += len(chunk)
                if size > config.MAX_UPLOAD_BYTES:
                    raise HTTPException(413,'Upload exceeds size limit')
                out.write(chunk)
        if not size:
            raise HTTPException(400,'Empty file')
        mid = db.create_meeting(Path(file.filename or 'recording').name,path,meta.model_dump(mode='json'))
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        file.file.close()
    return dict(meeting_id=mid,status='queued')

@app.get('/api/meetings')
def meetings():
    return {'meetings':db.list_meetings()}

@app.get('/api/meetings/{mid}')
def meeting(mid:int):
    m = required(mid)
    m.pop('path')
    return m

@app.put('/api/meetings/{mid}/draft')
def save(mid:int,body:WriteDraft):
    current = required(mid)
    ids = [s.id for s in body.draft.transcript]
    aids = [a.id for a in body.draft.assignments]
    if len(ids)!=len(set(ids)) or len(aids)!=len(set(aids)):
        raise HTTPException(422,'Duplicate segment or assignment IDs')
    old = current['draft']['transcript']
    new = [s.model_dump() for s in body.draft.transcript]
    # Source changes can temporarily leave stale evidence; approval enforces strict validation.
    if old == new and body.draft.reviewed:
        try:
            validate_evidence(body.draft,body.draft.transcript)
        except ValueError as e:
            raise HTTPException(422,str(e)) from None
    mutate(db.save_draft,mid,body.revision,body.draft.model_dump(mode='json'))
    return meeting(mid)

@app.post('/api/meetings/{mid}/approve')
def approve(mid:int,body:Revision):
    return {'version_id':mutate(db.approve,mid,body.revision)}

@app.post('/api/meetings/{mid}/retry')
def retry(mid:int,body:Revision):
    mutate(db.enqueue,mid,body.revision,False)
    return {'status':'queued'}

@app.post('/api/meetings/{mid}/reanalyze')
def reanalyze(mid:int,body:Revision):
    mutate(db.enqueue,mid,body.revision,True)
    return {'status':'queued'}

@app.post('/api/meetings/{mid}/candidate/apply')
def apply_candidate(mid:int,body:Revision):
    mutate(db.apply_candidate,mid,body.revision)
    return meeting(mid)

@app.get('/api/meetings/{mid}/versions/{vid}')
def version(mid:int,vid:int):
    v = db.version(mid,vid)
    if not v:
        raise HTTPException(404,'Version not found')
    return v

@app.get('/api/meetings/{mid}/audit')
def audit_detail(mid:int):
    required(mid)
    from sqlalchemy import text
    import json
    with db.engine.connect() as c:
        rows = c.execute(text('SELECT * FROM audit_v2 WHERE meeting_id=:m ORDER BY id'),dict(m=mid)).mappings()
        return [dict(id=r['id'],ts=r['ts'],action=r['action'],before=json.loads(r['before_json']),after=json.loads(r['after_json'])) for r in rows]

@app.get('/api/meetings/{mid}/audio')
def audio(mid:int):
    m = required(mid)
    original = Path(m['path']).resolve()
    path = original.with_suffix('.decoded.wav')
    if not path.is_relative_to(config.UPLOAD_DIR.resolve()) or not path.is_file():
        raise HTTPException(404,'Decoded audio is not available yet')
    return FileResponse(path,media_type='audio/wav')

@app.get('/api/assignments')
def assignments():
    rows = []
    for item in db.list_meetings():
        m = db.get_meeting(item['id'])
        today = datetime.now(ZoneInfo(m['metadata']['timezone'])).date().isoformat()
        for a in m['draft']['assignments']:
            rows.append(dict(**a,meeting_id=m['id'],title=m['metadata']['title'],revision=m['revision'],
                overdue=bool(a['deadline'] and a['deadline']<today and a['status'] in ('open','in_progress'))))
    return {'assignments':rows}

@app.get('/api/meetings/{mid}/export')
def export(mid:int,format:str='docx',version_id:int|None=None,include_transcript:bool=True):
    m = required(mid)
    snapshot = db.version(mid,version_id) if version_id is not None else dict(metadata=m['metadata'],draft=m['draft'],revision=m['revision'])
    if not snapshot:
        raise HTTPException(404,'Version not found')
    if not snapshot['draft']['transcript']:
        raise HTTPException(409,'No transcript available')
    if format not in ('docx','pdf'):
        raise HTTPException(400,'format must be docx or pdf')
    try:
        buf = (build_docx if format=='docx' else build_pdf)(snapshot,version_id is not None,include_transcript)
    except ValueError as e:
        raise HTTPException(409,str(e)) from None
    media = 'application/pdf' if format=='pdf' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    return Response(buf.getvalue(),media_type=media,headers={'Content-Disposition':f'attachment; filename="protocol_{mid}_{version_id or "draft"}.{format}"'})

@app.get('/')
def index():
    return FileResponse(config.ROOT / 'frontend/index.html')
app.mount('/static',StaticFiles(directory=config.ROOT/'frontend'),name='static')

if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host=config.HOST,port=config.PORT)
