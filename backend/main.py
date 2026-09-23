"""Хаттама AI — FastAPI backend (API + статический фронтенд)."""
from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

import config
import db
from agents.export import build_docx, build_pdf
from llm_client import LLM
from orchestrator import llm_status, run_pipeline

FRONTEND_DIR = Path(os.path.dirname(os.path.abspath(__file__))).parent / "frontend"

db.init_db()
app = FastAPI(title="Хаттама AI — автопротоколирование совещаний", version="0.1.0")


def _save(upload: UploadFile) -> tuple[str, str]:
    ext = Path(upload.filename or "").suffix.lower()
    if ext not in config.ALLOWED_EXT:
        raise HTTPException(400, f"Недопустимый формат: {ext}. Разрешены: {sorted(config.ALLOWED_EXT)}")
    name = f"{int(time.time())}_{uuid.uuid4().hex[:8]}{ext}"
    path = os.path.join(config.UPLOAD_DIR, name)
    with open(path, "wb") as f:
        chunk = upload.file.read(1024 * 1024)
        while chunk:
            f.write(chunk)
            chunk = upload.file.read(1024 * 1024)
    return upload.filename or name, path


# ---------------------------------------------------------------- API
@app.get("/api/health")
def health():
    return {"status": "ok", "llm": llm_status()}


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    original, path = _save(file)
    meeting_id = db.create_meeting(original, path)
    db.log_event(meeting_id, "upload", f"Файл {original} получен, запуск пайплайна")
    run_pipeline(meeting_id, path)
    return {"meeting_id": meeting_id, "status": "processing"}


@app.get("/api/meetings")
def meetings():
    items = db.list_meetings()
    return {"meetings": items}


@app.get("/api/meetings/{meeting_id}")
def meeting(meeting_id: int):
    m = db.get_meeting(meeting_id)
    if not m:
        raise HTTPException(404, "Совещание не найдено")
    for a in m.get("assignments", []):
        a["overdue"] = db.assignment_overdue(a.get("deadline"))
    return m


@app.patch("/api/meetings/{meeting_id}/assignments/{assignment_id}")
def set_status(meeting_id: int, assignment_id: int, body: dict):
    status = (body or {}).get("status")
    if status not in ("в работе", "выполнено", "просрочено"):
        raise HTTPException(400, "Недопустимый статус")
    db.set_assignment_status(assignment_id, status)
    return {"ok": True}


@app.get("/api/meetings/{meeting_id}/export")
def export(meeting_id: int, format: str = "docx"):
    m = db.get_meeting(meeting_id)
    if not m:
        raise HTTPException(404, "Совещание не найдено")
    if m["status"] != "done" or not m["result"]:
        raise HTTPException(409, "Протокол ещё не готов")
    meta = {
        "filename": m["filename"],
        "created_at": m["created_at"],
        "assignments": m["assignments"] or m["result"].get("assignments", []),
        "summary": m["result"].get("summary", []),
        "transcript": m["result"].get("transcript", []),
        "extract_mode": m.get("extract_mode"),
        "summary_mode": m.get("summary_mode"),
    }
    if format == "docx":
        buf = build_docx(meta)
        return Response(buf.getvalue(),
                        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        headers={"Content-Disposition": f'attachment; filename="protocol_{meeting_id}.docx"'})
    if format == "pdf":
        buf = build_pdf(meta)
        return Response(buf.getvalue(), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="protocol_{meeting_id}.pdf"'})
    raise HTTPException(400, "format: docx|pdf")


@app.get("/api/meetings/{meeting_id}/protocol.txt")
def protocol_txt(meeting_id: int):
    path = Path(config.OUTPUT_DIR) / f"{meeting_id}_protocol.txt"
    if not path.exists():
        raise HTTPException(404, "Протокол не готов")
    return FileResponse(path, media_type="text/plain; charset=utf-8",
                        filename=f"protocol_{meeting_id}.txt")


# ---------------------------------------------------------------- фронтенд
@app.get("/")
def index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=False)