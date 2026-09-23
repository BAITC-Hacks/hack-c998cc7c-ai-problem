"""Сшивка транскрипта с говорящими: реплики → блоки «Говорящий 1..N»."""
from __future__ import annotations

import numpy as np

import config
from agents.diarize import cluster_speakers, features_for_turns


def build_turns(segments: list[dict], gap: float | None = None) -> list[dict]:
    """Склеивает соседние сегменты Whisper в реплики (пауза внутри реплики < gap)."""
    gap = config.TURN_GAP if gap is None else gap
    turns: list[dict] = []
    for seg in segments:
        if turns and seg["start"] - turns[-1]["end"] < gap:
            turns[-1]["end"] = max(turns[-1]["end"], seg["end"])
            turns[-1]["segments"].append(seg)
        else:
            turns.append({"start": seg["start"], "end": seg["end"], "segments": [seg]})
    for t in turns:
        t["text"] = " ".join(s["text"] for s in t["segments"]).strip()
    return turns


def diarize(segments: list[dict], waveform: np.ndarray) -> list[dict]:
    """Возвращает блоки: [{start, end, speaker, text, segments}], speaker = 'Говорящий N'."""
    turns = build_turns(segments)
    n = len(turns)
    if n == 0:
        return []
    if n >= 2:
        feats = features_for_turns(waveform, turns)
        labels = cluster_speakers(feats)
    else:
        labels = [0]
    # упорядочить говорящих по первому появлению
    order: dict[int, int] = {}
    for l in labels:
        order.setdefault(l, len(order))
    blocks = []
    for t, lab in zip(turns, labels):
        idx = order[lab]
        blocks.append({
            "start": t["start"],
            "end": t["end"],
            "speaker": f"Говорящий {idx + 1}",
            "speaker_idx": idx,
            "text": t["text"],
            "segments": [dict(s) for s in t["segments"]],
        })
    return blocks