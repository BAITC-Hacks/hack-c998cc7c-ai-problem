from datetime import date, datetime
import re
from typing import Literal
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Metadata(Strict):
    title: str = Field(min_length=1, max_length=200)
    meeting_at: datetime
    timezone: str = "Asia/Qyzylorda"
    participants: list[str] = Field(default_factory=list, max_length=100)
    mode: Literal["LOCAL", "HYBRID", "RULES"] = "LOCAL"
    hybrid_consent: bool = False
    # Missing fields in historical meetings retain local audio processing.
    asr_mode: Literal["LOCAL", "API"] = "LOCAL"
    audio_consent: bool = False

    @field_validator("timezone")
    @classmethod
    def zone(cls, value):
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError:
            raise ValueError("Unknown IANA timezone")
        return value

    @model_validator(mode="after")
    def consent(self):
        if self.asr_mode == "API" and not self.audio_consent:
            raise ValueError("API ASR requires explicit audio transfer consent")
        if self.mode == "HYBRID" and not self.hybrid_consent:
            raise ValueError("HYBRID requires explicit transcript transfer consent")
        if self.meeting_at.tzinfo is None:
            self.meeting_at = self.meeting_at.replace(tzinfo=ZoneInfo(self.timezone))
        self.meeting_at = self.meeting_at.astimezone(ZoneInfo(self.timezone))
        return self


class Segment(Strict):
    id: str = Field(min_length=1, max_length=80)
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(ge=0, allow_inf_nan=False)
    text: str = Field(min_length=1, max_length=20000)
    speaker: str | None = Field(default=None, max_length=200)
    language: Literal["ru", "kk", "mixed", "unknown"] = "unknown"

    @model_validator(mode="after")
    def timing(self):
        if self.end < self.start:
            raise ValueError("Invalid segment timing")
        return self


class Evidence(Strict):
    segment_id: str
    quote: str = Field(min_length=1)
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def timing(self):
        if self.end < self.start:
            raise ValueError("Invalid evidence timing")
        return self


class Assignment(Strict):
    id: str = Field(default_factory=lambda: uuid4().hex)
    action: str = Field(min_length=1, max_length=10000)
    expected_result: str | None = None
    owner: str | None = None
    deadline_raw: str | None = None
    deadline: date | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    review: Literal["needs_review", "confirmed"] = "needs_review"
    uncertainty: list[str] = Field(default_factory=list)
    unspecified: list[Literal["owner", "deadline", "expected_result"]] = Field(
        default_factory=list
    )
    status: Literal["open", "in_progress", "done", "cancelled"] = "open"
    origin: Literal["extracted", "manual"] = "extracted"


class Statement(Strict):
    text: str = Field(min_length=1, max_length=20000)
    kind: Literal["decision", "proposal", "question"] = "decision"
    evidence: list[Evidence] = Field(default_factory=list)


class Analysis(Strict):
    summary: list[str] = Field(default_factory=list)
    decisions: list[Statement] = Field(default_factory=list)
    assignments: list[Assignment] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)


class Draft(Analysis):
    transcript: list[Segment] = Field(default_factory=list)
    reviewed: bool = False


def validate_evidence(analysis: Analysis, segments: list[Segment], require=True):
    lookup = {s.id: s for s in segments}
    for item in [*analysis.assignments, *analysis.decisions]:
        if (
            require
            and not item.evidence
            and getattr(item, "origin", "extracted") == "extracted"
        ):
            raise ValueError("Extracted item has no evidence")
        for e in item.evidence:
            if not evidence_in_transcript(e, segments, lookup):
                raise ValueError(
                    "Evidence must quote an existing contiguous transcript window "
                    "covering the stated timings"
                )


_WS = re.compile(r"\s+")


def _collapse(value):
    return _WS.sub(" ", str(value)).strip()


def evidence_in_transcript(evidence, segments, lookup, tolerance=0.5):
    """Ground a piece of evidence in the transcript.

    Times describe whole segments, not guessed word-level timestamps. The
    anchor must be the first segment actually quoted; a spanning quote must
    also reach the final segment, without skipping any intervening text.
    """
    anchor = lookup.get(evidence.segment_id)
    if anchor is None:
        return False
    if (evidence.end < evidence.start
            or abs(evidence.start - anchor.start) > tolerance):
        return False
    quote = _collapse(evidence.quote)
    if not quote:
        return False
    idx = next(
        (i for i, s in enumerate(segments) if s.id == evidence.segment_id), None
    )
    if idx is None:
        return False
    window = ""
    first_length = len(_collapse(anchor.text))
    for segment in segments[idx:]:
        if segment.end > evidence.end + tolerance:
            break
        last_start = len(window) + (1 if window else 0)
        window += (" " if window else "") + _collapse(segment.text)
        if abs(evidence.end - segment.end) > tolerance:
            continue
        position = window.find(quote)
        while 0 <= position < first_length:
            if position + len(quote) > last_start:
                return True
            position = window.find(quote, position + 1)
    return False
