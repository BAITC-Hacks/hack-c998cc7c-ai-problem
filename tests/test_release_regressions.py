"""Release regressions: grounded evidence and recoverable, honest transcripts."""

import httpx
import pytest

from test_pipeline import store  # Reuse the isolated real SQLite fixture.
import config
import db
import diarization
import orchestrator
from schemas import Analysis, Evidence, Metadata, Segment, Statement, validate_evidence


def transcript_segment(identifier, text, start, end, **kwargs):
    return Segment(id=identifier, text=text, start=start, end=end, **kwargs)


def evidenced_statement(anchor, quote, start, end):
    return Analysis(
        decisions=[
            Statement(
                text="Решение для проверки источника",
                evidence=[Evidence(segment_id=anchor, quote=quote, start=start, end=end)],
            )
        ]
    )


@pytest.mark.parametrize(
    "anchor,quote,start,end",
    [
        ("s1", "Согласовали бюджет.", 0, 5),
        ("s2", "Обсудили план.", 60, 65),
    ],
)
def test_quote_cannot_point_to_a_different_segment(anchor, quote, start, end):
    segments = [
        transcript_segment("s1", "Обсудили план.", 0, 5),
        transcript_segment("s2", "Согласовали бюджет.", 60, 65),
    ]
    with pytest.raises(ValueError):
        validate_evidence(evidenced_statement(anchor, quote, start, end), segments)


def test_evidence_cannot_have_reversed_timestamps():
    with pytest.raises(ValueError):
        Evidence(segment_id="s1", quote="Обсудили план.", start=5, end=0)


def test_quote_can_span_adjacent_segments_with_the_first_segment_as_anchor():
    segments = [
        transcript_segment("s1", "Обсудили план. Поручаю Айдане", 0, 5),
        transcript_segment("s2", "подготовить отчёт. Следующий вопрос.", 5, 10),
    ]
    validate_evidence(
        evidenced_statement("s1", "Поручаю Айдане подготовить отчёт.", 0, 10),
        segments,
    )


def test_spanning_quote_cannot_skip_an_intermediate_segment():
    segments = [
        transcript_segment("s1", "Поручаю Айдане", 0, 5),
        transcript_segment("s2", "Перерыв для обсуждения бюджета.", 5, 10),
        transcript_segment("s3", "подготовить отчёт.", 10, 15),
    ]
    with pytest.raises(ValueError):
        validate_evidence(
            evidenced_statement("s1", "Поручаю Айдане подготовить отчёт.", 0, 15),
            segments,
        )


@pytest.mark.parametrize("start,end", [(1, 5), (0, 4), (1, 4), (0, 5.6)])
def test_evidence_boundaries_must_match_the_quoted_segments(start, end):
    segments = [
        transcript_segment("s1", "Обсудили план.", 0, 5),
        transcript_segment("s2", "Согласовали бюджет.", 5, 10),
    ]
    with pytest.raises(ValueError):
        validate_evidence(
            evidenced_statement("s1", "Обсудили план.", start, end), segments
        )


def test_evidence_allows_small_timestamp_rounding():
    segments = [transcript_segment("s1", "Обсудили план.", 0, 5)]
    validate_evidence(
        evidenced_statement("s1", "Обсудили план.", 0.4, 4.6), segments
    )


@pytest.mark.parametrize("quote", ["Обсудили план.", "Согласовали бюджет."])
def test_spanning_quote_must_include_both_boundary_segments(quote):
    segments = [
        transcript_segment("s1", "Обсудили план.", 0, 5),
        transcript_segment("s2", "Согласовали бюджет.", 5, 10),
    ]
    with pytest.raises(ValueError):
        validate_evidence(evidenced_statement("s1", quote, 0, 10), segments)


def test_diarization_timeout_preserves_paid_asr_and_allows_reanalysis(store, monkeypatch):
    segments = [
        transcript_segment("s1", "Айдана, подготовь отчёт.", 0, 5, language="ru")
    ]
    meta = Metadata(
        title="Сохранить оплаченный транскрипт",
        meeting_at="2026-09-23T10:00:00",
        mode="RULES",
        asr_mode="API",
        audio_consent=True,
    )
    mid = db.create_meeting("meeting.wav", store / "meeting.wav", meta.model_dump(mode="json"))
    asr_calls = []

    def transcribe(path, progress):
        asr_calls.append(path)
        return segments

    def timed_out(*args, **kwargs):
        raise httpx.ReadTimeout("Speaker service did not respond")

    monkeypatch.setattr(orchestrator, "decode", lambda *args: None)
    monkeypatch.setattr(orchestrator, "transcribe_api", transcribe)
    monkeypatch.setattr(orchestrator, "diarize", timed_out)
    monkeypatch.setattr(
        orchestrator, "analyze", lambda *args: Analysis(summary=["Отчёт поручен Айдане."])
    )

    orchestrator.process(db.claim())
    failed = db.get_meeting(mid)
    saved_transcript = [s.model_dump(mode="json") for s in segments]
    assert failed["status"] == "error"
    assert failed["checkpoint"] == saved_transcript
    assert failed["draft"]["transcript"] == saved_transcript

    db.enqueue(mid, failed["revision"], analysis_only=True)
    orchestrator.process(db.claim())
    recovered = db.get_meeting(mid)
    assert recovered["status"] == "done", recovered["error"]
    assert recovered["candidate"]["transcript"] == saved_transcript
    assert recovered["candidate"]["summary"] == ["Отчёт поручен Айдане."]
    assert len(asr_calls) == 1


@pytest.mark.parametrize("mode", ["RULES", "LOCAL", "HYBRID"])
def test_diarization_never_invents_speakers_from_pauses_or_text(mode, tmp_path, monkeypatch):
    segments = [
        transcript_segment("s1", "Айдана, подготовь отчёт.", 0, 5),
        transcript_segment("s2", "Да, это тот же говорящий после паузы.", 30, 35),
    ]
    monkeypatch.setattr(config, "LLM_HYBRID_URL", "https://text.example/v1")
    monkeypatch.setattr(config, "LLM_HYBRID_MODEL", "test-model")
    monkeypatch.setattr(config, "LLM_API_KEY", "test-only-key")

    def no_external_client(*args, **kwargs):
        pytest.fail("Speaker identity must not be inferred by an external text LLM")

    monkeypatch.setattr(httpx, "Client", no_external_client)
    result = diarization.diarize(mode, segments, tmp_path / "absent.wav")
    assert [s.speaker for s in result] == [None, None]


@pytest.mark.parametrize("mode", ["RULES", "LOCAL", "HYBRID"])
def test_diarization_preserves_existing_speakers_and_language(mode, tmp_path, monkeypatch):
    segments = [
        transcript_segment("s1", "Жобаны талқылайық.", 0, 5, speaker="Айдана", language="kk"),
        transcript_segment("s2", "Обсудим сроки.", 30, 35, language="ru"),
    ]

    def no_external_client(*args, **kwargs):
        pytest.fail("Manual speaker review must not invoke a text model")

    monkeypatch.setattr(httpx, "Client", no_external_client)
    result = diarization.diarize(mode, segments, tmp_path / "absent.wav")
    assert [s.model_dump() for s in result] == [s.model_dump() for s in segments]
