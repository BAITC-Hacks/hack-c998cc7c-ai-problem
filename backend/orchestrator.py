"""Агентный оркестратор: запускает этапы, проксирует статусы, хранит результат."""
from __future__ import annotations

import threading
import traceback
from datetime import datetime
from pathlib import Path

import config
import db
from agents.align import diarize
from agents.export import build_text_protocol
from agents.extract import extract_assignments
from agents.summarize import summarize
from agents.transcribe import transcribe_audio
from faster_whisper.audio import decode_audio
from llm_client import get_llm, LLM_STATUS

STAGES = [
    ("transcribe", "Распознавание речи (локально)"),
    ("diarize", "Диаризация говорящих"),
    ("extract", "Извлечение поручений"),
    ("summarize", "Саммари"),
    ("export", "Экспорт протокола"),
]

_threads: dict[int, threading.Thread] = {}


def run_pipeline(meeting_id: int, file_path: str) -> None:
    def worker():
        try:
            db.set_stage(meeting_id, "processing", "transcribe")
            db.log_event(meeting_id, "transcribe", "Запущено распознавание речи моделью Whisper")
            segments = transcribe_audio(file_path)
            if not segments:
                db.fail_meeting(meeting_id, "Не удалось распознать речь")
                return
            db.log_event(meeting_id, "transcribe",
                         f"Распознано сегментов: {len(segments)}")
            db.set_stage(meeting_id, "processing", "diarize")
            waveform = decode_audio(file_path, sampling_rate=16000)
            blocks = diarize(segments, waveform)
            db.log_event(meeting_id, "diarize",
                         f"Говорящих: {len({b['speaker'] for b in blocks})}")
            db.set_stage(meeting_id, "processing", "extract")

            llm = get_llm()
            ex = extract_assignments(blocks, llm)
            db.log_event(meeting_id, "extract",
                         f"Поручений: {len(ex['assignments'])} (источник: {ex['mode']})")
            db.set_stage(meeting_id, "processing", "summarize")
            su = summarize(blocks, ex["assignments"], llm)
            db.log_event(meeting_id, "summarize", f"Пунктов саммари: {len(su['summary'])}")

            meeting = {
                "filename": file_path.split("/")[-1],
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "transcript": blocks,
                "assignments": ex["assignments"],
                "summary": su["summary"],
            }
            # текстовый протокол для скачивания
            proto_path = Path(config.OUTPUT_DIR) / f"{meeting_id}_protocol.txt"
            proto_path.write_text(build_text_protocol(meeting), encoding="utf-8")

            db.set_stage(meeting_id, "done", "export")
            db.finish_meeting(meeting_id, meeting, ex["mode"], su["mode"])
            db.log_event(meeting_id, "export", "Протокол сформирован и сохранён")
        except Exception as e:
            traceback.print_exc()
            db.log_event(meeting_id, "error", str(e)[:1000])
            db.fail_meeting(meeting_id, str(e))

    t = threading.Thread(target=worker, daemon=True, name=f"meeting-{meeting_id}")
    _threads[meeting_id] = t
    t.start()


def llm_status() -> dict:
    p = LLM_STATUS["provider"]
    return {
        "provider": p,
        "detail": LLM_STATUS["detail"],
        "available": p != "none",
    }