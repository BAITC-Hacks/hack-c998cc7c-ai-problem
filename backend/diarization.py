"""Speaker attribution boundary: preserve known identities without guessing.

Pauses identify silences, not distinct people, and text alone cannot identify
a voice. Until an acoustic diarization provider is configured, unknown speakers
stay unknown and the editor supports assigning them manually.
"""


def diarize(mode, segments, path=None, progress=lambda _: None):
    """Keep ASR/provider metadata intact without extra remote inference."""
    return segments
