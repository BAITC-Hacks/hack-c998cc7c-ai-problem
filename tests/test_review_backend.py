"""Review regressions: source grounding, real speaker identity and queue recovery."""

import httpx
import pytest
from sqlalchemy.exc import OperationalError

from test_pipeline import segment
from schemas import Analysis, Evidence, Segment, validate_evidence
from diarization import diarize
import db
import orchestrator


def test_evidence_rejects_reversed_timestamps():
    with pytest.raises(ValueError):
        Evidence(segment_id="s1", quote="Source", start=4, end=1)


@pytest.mark.parametrize(
    "anchor,quote,start,end",
    [
        ("s1", "Source one.", 7, 8),
        ("s1", "A distant decision.", 0, 5),
        ("s1", "A distant decision.", 20, 25),
    ],
)
def test_evidence_cannot_quote_outside_anchored_time_window(anchor, quote, start, end):
    transcript = [
        segment("Source one.", "s1", 0),
        segment("Unrelated discussion.", "s2", 10),
        segment("A distant decision.", "s3", 20),
    ]
    analysis = Analysis(assignments=[dict(action="Decision", evidence=[dict(
        segment_id=anchor, quote=quote, start=start, end=end,
    )])])
    with pytest.raises(ValueError, match="Evidence"):
        validate_evidence(analysis, transcript)


def test_evidence_accepts_sentence_split_across_adjacent_segments():
    transcript = [segment("Решили запустить", "s1", 0), segment("пилот в октябре.", "s2", 5)]
    analysis = Analysis(decisions=[dict(text="Запустить пилот", evidence=[dict(
        segment_id="s1", quote="запустить пилот", start=0, end=10,
    )])])
    validate_evidence(analysis, transcript)


@pytest.mark.parametrize("mode", ["RULES", "LOCAL", "HYBRID"])
def test_diarization_preserves_known_speakers_and_unknowns_without_guessing(mode, monkeypatch):
    transcript = [
        Segment(id="s1", start=0, end=1, text="Сәлем.", language="kk", speaker="Айдана"),
        Segment(id="s2", start=4, end=5, text="Привет.", language="ru"),
    ]
    monkeypatch.setattr(httpx.Client, "post", lambda *args, **kwargs: pytest.fail("Text cannot identify a voice"))
    result = diarize(mode, transcript, "missing.wav")
    assert [s.model_dump() for s in result] == [s.model_dump() for s in transcript]


def test_queue_recovers_from_temporary_database_lock(monkeypatch):
    class StopAfterRecovery:
        recovered = False
        delays = []

        def is_set(self):
            return self.recovered

        def wait(self, seconds):
            self.delays.append(seconds)

    stop = StopAfterRecovery()
    calls = []

    def claim():
        calls.append(True)
        if len(calls) == 1:
            raise OperationalError("SELECT ...", {}, Exception("database is locked"))
        stop.recovered = True
        return None

    monkeypatch.setattr(orchestrator, "_stop", stop)
    monkeypatch.setattr(db, "claim", claim)
    orchestrator.loop()
    assert len(calls) == 2
    assert stop.delays and stop.delays[0] >= 1


def test_queue_retries_persisting_failure_without_repeating_external_processing(monkeypatch):
    class StopAfterRecovery:
        recovered = False

        def is_set(self):
            return self.recovered

        def wait(self, seconds):
            pass

    stop = StopAfterRecovery()
    claims, processed, failures = [], [], []

    def claim():
        claims.append(True)
        if len(claims) > 1:
            stop.recovered = True
            return None
        return {"id": 42}

    def process(meeting):
        processed.append(meeting["id"])
        raise OperationalError("UPDATE ...", {}, Exception("database is locked"))

    def fail(mid, message):
        failures.append((mid, message))
        if len(failures) == 1:
            raise OperationalError("UPDATE ...", {}, Exception("database is locked"))

    monkeypatch.setattr(orchestrator, "_stop", stop)
    monkeypatch.setattr(db, "claim", claim)
    monkeypatch.setattr(orchestrator, "process", process)
    monkeypatch.setattr(db, "fail", fail)
    orchestrator.loop()
    assert processed == [42]
    assert len(failures) == 2
    assert failures[-1][0] == 42
