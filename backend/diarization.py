"""Replaceable diarization boundary. Unknown is preferable to invented identities."""

from typing import Protocol
from schemas import Segment


class Diarizer(Protocol):
    def assign(self, path: str, segments: list[Segment]) -> list[Segment]: ...


class ManualDiarizer:
    def assign(self, path, segments):
        return segments
