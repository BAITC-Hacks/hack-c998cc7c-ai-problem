"""A durable single-worker queue, with OS process lock and checkpoint recovery."""

import os
import threading
import wave
from pathlib import Path
import subprocess
import logging
from sqlalchemy.exc import OperationalError
import config
import db
from agents.transcribe import transcribe_audio
from agents.transcribe_api import transcribe_api
from diarization import diarize
from llm_client import ProcessingError, analyze
from schemas import Draft, Metadata, Segment

_stop = threading.Event()
_thread = None
_lock_file = None
_logger = logging.getLogger(__name__)


def decode(path, output):
    """FFmpeg is called with an argument vector, bounded time/duration and no network protocols."""
    tmp = output.with_suffix(".partial.wav")
    try:
        result = subprocess.run(
            [
                config.FFMPEG,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-protocol_whitelist",
                "file,pipe",
                "-i",
                str(path),
                "-map",
                "0:a:0",
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-t",
                str(config.MAX_AUDIO_SECONDS + 1),
                "-f",
                "wav",
                str(tmp),
            ],
            capture_output=True,
            timeout=600,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if result.returncode:
            raise ProcessingError(
                "AUDIO_DECODE_FAILED: invalid media or no audio stream"
            )
        with wave.open(str(tmp), "rb") as wav:
            seconds = wav.getnframes() / wav.getframerate()
            if seconds <= 0 or seconds > config.MAX_AUDIO_SECONDS:
                raise ProcessingError(
                    "AUDIO_DURATION_LIMIT: empty audio or recording longer than configured maximum"
                )
        tmp.replace(output)
    except FileNotFoundError:
        raise ProcessingError(
            "FFMPEG_MISSING: install FFmpeg and configure FFMPEG in backend/.env"
        ) from None
    except subprocess.TimeoutExpired:
        raise ProcessingError(
            "AUDIO_DECODE_TIMEOUT: FFmpeg exceeded 600 seconds"
        ) from None
    finally:
        tmp.unlink(missing_ok=True)


def process(m):
    mid = m["id"]
    try:
        metadata = Metadata.model_validate(m["metadata"])
        if m["checkpoint"] is not None:
            segments = [Segment.model_validate(s) for s in m["checkpoint"]]
        else:
            db.stage(mid, "decode")
            normalized = Path(m["path"]).with_suffix(".decoded.wav")
            decode(m["path"], normalized)
            db.stage(mid, "transcribe")
            segments = (transcribe_api(normalized, lambda stage: db.stage(mid, stage))
                        if metadata.asr_mode == "API" else transcribe_audio(normalized))
            if not segments:
                raise ProcessingError(
                    "NO_SPEECH: no speech recognized; no minutes were generated"
                )
            segments = diarize(
                metadata.mode, segments, normalized,
                lambda stage: db.stage(mid, stage),
            )
            db.stage(mid, "diarization_manual", [s.model_dump() for s in segments])
        db.stage(mid, "analyze")
        result = analyze(
            segments,
            metadata,
            lambda stage: db.stage(mid, stage),
        )
        draft = Draft(**result.model_dump(), transcript=segments)
        db.finish(mid, draft.model_dump(mode="json"), bool(m["analysis_only"]))
    except ProcessingError as e:
        db.fail(mid, str(e))
    except Exception:
        # Never persist remote response bodies, credentials or full transcripts in error logs.
        db.fail(
            mid,
            "PROCESSING_FAILED: internal processing error; inspect installation and retry",
        )


def loop():
    pending_failure = None
    while not _stop.is_set():
        try:
            if pending_failure is not None:
                # Persist the terminal state before taking another job. Retrying
                # the whole process here could repeat a paid external request.
                db.fail(pending_failure, "PROCESSING_FAILED: database unavailable during processing; retry after recovery")
                pending_failure = None
                continue
            m = db.claim()
            if m:
                try:
                    process(m)
                except OperationalError:
                    pending_failure = m["id"]
                    raise
            else:
                _stop.wait(1)
        except OperationalError:
            # A temporary SQLite lock must not permanently kill the only worker.
            _logger.warning("Queue database unavailable; retrying in 5 seconds")
            _stop.wait(5)


def start():
    global _thread, _lock_file
    lock = open(config.DATA_DIR / "worker.lock", "a+b")
    try:
        lock.seek(0)
        if os.name == "nt":
            import msvcrt

            if lock.read(1) == b"":
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock.close()
        return False
    _lock_file = lock
    db.recover()
    _stop.clear()
    _thread = threading.Thread(target=loop, daemon=True, name="khattama-worker")
    _thread.start()
    return True


def stop():
    global _lock_file
    _stop.set()
    if _thread:
        _thread.join(timeout=2)
    # Keep lock held if a job is still running. Process exit releases it safely.
    if _lock_file and (not _thread or not _thread.is_alive()):
        _lock_file.close()
        _lock_file = None
