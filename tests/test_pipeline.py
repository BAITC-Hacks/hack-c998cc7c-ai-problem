"""Тесты Хаттама AI: юнит (быстрые) + e2e полный пайплайн (могут быть медленными).

Быстрый прогон:        pytest tests/ -m "not slow"
Полный (жюри/демо):   pytest tests/ -m slow
Все:                  pytest tests/
"""
from __future__ import annotations

import io
import os
from datetime import date

import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from date_parser import normalize_deadline
from agents.diarize import cluster_speakers
from agents.align import build_turns
from agents.extract import extract_assignments_rules, bind_owner_to_speaker
from agents.export import build_docx, build_pdf, build_text_protocol

SAMPLES = os.path.join(os.path.dirname(__file__), "..", "samples")
SAMPLE_1 = os.path.join(SAMPLES, "meeting_1_ru_kz.mp3")

SUITE = ["fast", "slow"]


@pytest.fixture
def llm_none(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "")
    import llm_client
    monkeypatch.setattr(llm_client, "_llm_singleton", None)
    return llm_client.get_llm()


@pytest.fixture
def blocks():
    return [
        {"start": 0.0, "end": 3.0, "speaker": "Говорящий 1", "speaker_idx": 0,
         "text": "Поручаю Кайрату подготовить отчёт к пятнице."},
        {"start": 4.0, "end": 7.0, "speaker": "Говорящий 2", "speaker_idx": 1,
         "text": "Қанат, осы аптада жоспарды дайындасыз."},
        {"start": 8.0, "end": 10.0, "speaker": "Говорящий 1", "speaker_idx": 0,
         "text": "Спасибо, а также необходимо направить письмо в Министерство к 30 сентября."},
    ]


# ---------------------------------------------------------------- fast
@pytest.mark.slow
class TestDateParser:
    @pytest.mark.parametrize("phrase,expected", [
        ("к пятнице", "2026-09-25"),
        ("до конца недели", "2026-09-27"),
        ("через 3 дня", "2026-09-26"),
        ("завтра", "2026-09-24"),
        ("послезавтра", "2026-09-25"),
        ("до 28.09", "2026-09-28"),
        ("по 30 сентября", "2026-09-30"),
        ("до 15.12.2026", "2026-12-15"),
        ("к жұма", "2026-09-25"),
    ], ids=lambda x: str(x))
    def test_phrases(self, phrase, expected):
        assert normalize_deadline(phrase, date(2026, 9, 23)) == expected

    def test_none(self):
        assert normalize_deadline("обсудили повестку", date(2026, 9, 23)) is None


class TestRules:
    def test_extraction(self, blocks):
        out = extract_assignments_rules(blocks)
        assert len(out) >= 2
        assert any(a["owner"] == "Кайрату" for a in out)
        assert any(a["deadline"] == "2026-09-25" for a in out)
        assert any("Министерств" in a["task"] for a in out)

    def test_bind(self, blocks):
        b = bind_owner_to_speaker("Кайрат", blocks)
        assert b and b["speaker_label"] == "Говорящий 1"

    def test_offline_pipeline(self, blocks, llm_none):
        from agents.summarize import summarize
        ex = extract_assignments_rules(blocks)
        su = summarize(blocks, ex, llm_none)
        assert llm_none.available is False
        assert su["summary"] and su["mode"] == "rules"


class TestTurnsCluster:
    def test_turns_merge(self, blocks):
        segs = [s for b in blocks for s in (
            {"start": b["start"], "end": b["end"], "text": b["text"]},)]
        turns = build_turns(segs, gap=1.0)
        assert len(turns) == len(segs)

    def test_cluster_reproducible(self):
        import numpy as np
        X = np.array([[1.0, 2.0], [1.1, 2.0], [50.0, 60.0], [52.0, 58.0]])
        labels = cluster_speakers(X)
        assert len(set(labels)) >= 2
        assert labels[0] == labels[1] != labels[2]


class TestExport:
    def _meeting(self):
        return {
            "filename": "meeting.mp3",
            "created_at": "2026-09-23T00:00:00",
            "extract_mode": "rules", "summary_mode": "rules",
            "summary": ["Обсудили план.", "Назначен ответственный."],
            "assignments": [{"task": "Подготовить отчёт", "owner": "Кайрат",
                             "deadline": "2026-09-25", "priority": "high",
                             "speaker_label": "Говорящий 1"}],
            "transcript": [{"start": 0, "end": 5, "speaker": "Говорящий 1",
                            "text": "Поручаю Кайрату подготовить отчёт."}],
        }

    def test_docx(self):
        buf = build_docx(self._meeting())
        assert buf.getvalue().startswith(b"PK")

    def test_pdf(self):
        buf = build_pdf(self._meeting())
        assert buf.getvalue().startswith(b"%PDF")

    def test_txt(self):
        out = build_text_protocol(self._meeting())
        assert "ПРОТОКОЛ" in out and "Подготовить отчёт" in out


# ---------------------------------------------------------------- slow: full e2e
@pytest.mark.slow
def test_full_pipeline_on_sample_sample_1(llm_none):
    path = SAMPLE_1
    if not os.path.exists(path):
        pytest.skip("samples/meeting_1_ru_kz.mp3 отсутствует")
    from agents.transcribe import transcribe_audio
    from agents.align import diarize
    from faster_whisper.audio import decode_audio
    from agents.extract import extract_assignments_rules
    from agents.summarize import summarize

    segments = transcribe_audio(path)
    assert len(segments) > 3, "транскрипт пуст"
    wav = decode_audio(path, sampling_rate=16000)
    blocks = diarize(segments, wav)
    assert blocks, "нет реплик после диаризации"
    assert len({b["speaker"] for b in blocks}) >= 1
    text_len = sum(len(b["text"]) for b in blocks)
    assert text_len > 50
    ex = extract_assignments_rules(blocks)
    su = summarize(blocks, ex, llm_none)
    assert su["summary"]
    docx = build_docx({"filename": "test", "created_at": "x", "assignments": ex,
                       "summary": su["summary"], "transcript": blocks})
    assert docx.getvalue().startswith(b"PK")
    print(f"  [e2e] сегментов={len(segments)}, говорящих={len({b['speaker'] for b in blocks})}, "
          f"поручений={len(ex)}, текста={text_len} символов")