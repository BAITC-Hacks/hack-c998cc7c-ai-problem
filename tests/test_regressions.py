"""Regression contracts for review integrity and cumulative LLM analysis."""

import copy
import json

import httpx
import pytest

from test_pipeline import create_ready, segment, store
import config
import db
import llm_client
from schemas import Metadata


@pytest.mark.parametrize(
    "field,value",
    [
        ("summary", ["Updated summary"]),
        ("decisions", [{"text": "Updated decision", "kind": "decision", "evidence": []}]),
        ("questions", ["Who approves the budget?"]),
    ],
)
def test_editing_reviewed_document_content_requires_new_review(store, field, value):
    mid = create_ready(store)
    meeting = db.get_meeting(mid)
    draft = meeting["draft"]
    draft["reviewed"] = True
    db.save_draft(mid, meeting["revision"], draft)
    meeting = db.get_meeting(mid)
    assert meeting["draft"]["reviewed"] is True

    meeting["draft"][field] = value
    db.save_draft(mid, meeting["revision"], meeting["draft"])

    saved = db.get_meeting(mid)
    assert saved["draft"][field] == value
    assert saved["draft"]["reviewed"] is False
    with pytest.raises(ValueError, match="Review"):
        db.approve(mid, saved["revision"])


def mock_llm(monkeypatch, replies):
    """Stub only the external model; exercise real parsing and validation."""
    monkeypatch.setattr(config, "LLM_LOCAL_URL", "http://127.0.0.1:8080/v1")
    monkeypatch.setattr(config, "LLM_LOCAL_MODEL", "test-model")
    calls = []

    def reply(self, *args, **kwargs):
        calls.append(kwargs)
        output = replies[min(len(calls) - 1, len(replies) - 1)]
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(output)}}]},
            request=httpx.Request("POST", "http://127.0.0.1:8080/v1/chat/completions"),
        )

    monkeypatch.setattr(httpx.Client, "post", reply)
    return calls


def test_llm_cannot_claim_manual_origin_to_bypass_evidence(monkeypatch):
    calls = mock_llm(
        monkeypatch,
        [{"assignments": [{"id": "fake", "action": "Fabricated task", "origin": "manual", "evidence": []}]}],
    )

    with pytest.raises(llm_client.ProcessingError, match="LLM_INVALID_JSON"):
        llm_client.analyze(
            [segment("We discussed the budget.")],
            Metadata(title="Review", meeting_at="2026-09-23"),
        )
    assert len(calls) == 2


def test_later_chunks_preserve_previous_summary_decisions_and_questions(monkeypatch):
    first = segment("Use the existing budget. Who approves it?")
    second = segment("Schedule the next meeting. Which day?", "s2", 5)
    previous_decision = {
        "text": "Use the existing budget.",
        "kind": "decision",
        "evidence": [{"segment_id": first.id, "quote": "Use the existing budget.", "start": first.start, "end": first.end}],
    }
    next_decision = {
        "text": "Schedule the next meeting.",
        "kind": "decision",
        "evidence": [{"segment_id": second.id, "quote": "Schedule the next meeting.", "start": second.start, "end": second.end}],
    }
    monkeypatch.setattr(llm_client, "chunks", lambda segments: [[first], [second]])
    mock_llm(
        monkeypatch,
        [
            {"summary": ["The budget is retained."], "decisions": [previous_decision], "questions": ["Who approves it?"]},
            {"summary": ["A follow-up meeting is needed."], "decisions": [next_decision], "questions": ["Which day?"]},
        ],
    )

    result = llm_client.analyze(
        [first, second], Metadata(title="Review", meeting_at="2026-09-23")
    )

    assert result.summary == ["The budget is retained.", "A follow-up meeting is needed."]
    assert [d.model_dump() for d in result.decisions] == [previous_decision, next_decision]
    assert result.questions == ["Who approves it?", "Which day?"]


def test_candidate_cannot_overwrite_subsequently_edited_transcript(store):
    mid = create_ready(store)
    meeting = db.get_meeting(mid)
    db.enqueue(mid, meeting["revision"], True)
    db.finish(mid, copy.deepcopy(meeting["draft"]), True)
    meeting = db.get_meeting(mid)
    assert meeting["candidate"] is not None

    draft = meeting["draft"]
    draft["transcript"][0]["text"] = "Corrected source text after analysis finished."
    db.save_draft(mid, meeting["revision"], draft)
    saved = db.get_meeting(mid)

    with pytest.raises(ValueError):
        db.apply_candidate(mid, saved["revision"])
    assert db.get_meeting(mid)["draft"]["transcript"] == draft["transcript"]


def test_repeated_decisions_merge_evidence_without_duplicates(monkeypatch):
    first = segment("Keep the budget.")
    second = segment("Keep the budget.", "s2", 5)
    evidence = [
        dict(segment_id=s.id, quote=s.text, start=s.start, end=s.end)
        for s in (first, second)
    ]
    monkeypatch.setattr(llm_client, "chunks", lambda segments: [[first], [second]])
    mock_llm(monkeypatch, [
        dict(summary=["Budget retained."], questions=["Who approves?"], decisions=[
            dict(text="Keep the budget.", kind="decision", evidence=[evidence[0]])
        ]),
        dict(summary=["Budget retained."], questions=["Who approves?"], decisions=[
            dict(text="Keep the budget.", kind="decision", evidence=[evidence[1], evidence[1]])
        ]),
    ])

    result = llm_client.analyze(
        [first, second], Metadata(title="Review", meeting_at="2026-09-23")
    )

    assert len(result.decisions) == 1
    assert [e.model_dump() for e in result.decisions[0].evidence] == evidence
    assert result.summary == ["Budget retained."]
    assert result.questions == ["Who approves?"]


def test_final_chunk_cannot_exceed_analysis_context_limit(monkeypatch):
    mock_llm(monkeypatch, [{"summary": ["x" * 60001]}])
    with pytest.raises(llm_client.ProcessingError, match="ANALYSIS_CONTEXT_LIMIT"):
        llm_client.analyze(
            [segment("Budget discussion.")],
            Metadata(title="Review", meeting_at="2026-09-23"),
        )


def test_assignment_listing_returns_only_register_data(store):
    first = create_ready(store)
    second = create_ready(store)
    rows = db.list_assignment_drafts()
    assert [row["id"] for row in rows] == [second, first]
    assert set(rows[0]) == {"id", "metadata", "draft", "revision"}
    assert rows[0]["revision"] == db.get_meeting(second)["revision"]
    assert rows[0]["draft"] == db.get_meeting(second)["draft"]
