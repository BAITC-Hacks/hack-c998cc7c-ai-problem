"""Агент распознавания речи: faster-whisper (локально, без облака).

Выход: сегменты {start, end, text, language}.
Язык определяется автоматически по сегменту → поддержка русского, казахского
и смешанной («шала-казах») речи на одном совещании.
"""
from __future__ import annotations

import re
import threading

import config
from faster_whisper import WhisperModel

_fw_lock = threading.Lock()
_fw_model: WhisperModel | None = None


def _load_model() -> WhisperModel:
    global _fw_model
    with _fw_lock:
        if _fw_model is None:
            _fw_model = WhisperModel(
                config.WHISPER_MODEL,
                device=config.WHISPER_DEVICE,
                compute_type=config.WHISPER_COMPUTE,
            )
        return _fw_model


_PUNCT = ".,!?;:.…-–—"


def _clean(text: str) -> str:
    """Подчистка текста сегмента: схлопывание пробелов, пробелы вокруг пунктуации."""
    text = re.sub(r"\s+", " ", text.strip())
    out = ""
    for ch in text:
        if ch in "!?;:,.…":
            out = out.rstrip()
            out += ch + " "
            continue
        if ch == "-":
            out += " - "
            continue
        if ch == "«":
            out = out.rstrip()
            out += " «"
            continue
        if ch in '")»':
            out = out.rstrip()
            out += ch
            continue
        if ch == "(":
            out = out.rstrip()
            out += " ("
            continue
        out += ch
    out = re.sub(r"\s+", " ", out)
    return out.strip()


def transcribe_audio(path: str) -> list[dict]:
    """Возвращает список сегментов: [{start, end, text, prob}]."""
    model = _load_model()
    segments, info = model.transcribe(
        path,
        language=config.WHISPER_LANGUAGE,
        vad_filter=config.VAD_FILTER,
        beam_size=config.BEAM_SIZE,
    )
    result = []
    for seg in segments:
        text = _clean(seg.text)
        if not text or len(text) < 2:
            continue
        result.append({
            "start": round(float(seg.start), 2),
            "end": round(float(seg.end), 2),
            "text": text,
            "prob": round(float(seg.avg_logprob), 3) if seg.avg_logprob is not None else None,
        })
    return result