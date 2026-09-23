"""Real audio decoding / optional ASR tests. No transcript mocks here."""

import os
import re
import sys
import wave
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import config
from orchestrator import decode
from llm_client import ProcessingError
from agents.transcribe import transcribe_audio


@pytest.fixture
def silence(tmp_path):
    path = tmp_path / "silence.wav"
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(b"\0" * (16000 * 2 * 3))
    return path


def test_real_ffmpeg_decode_and_corrupt_file(silence, tmp_path):
    output = tmp_path / "decoded.wav"
    decode(silence, output)
    with wave.open(str(output), "rb") as f:
        assert f.getframerate() == 16000 and f.getnframes() == 48000
    corrupt = tmp_path / "bad.mp4"
    corrupt.write_bytes(b"not media")
    with pytest.raises(ProcessingError, match="AUDIO_DECODE_FAILED"):
        decode(corrupt, tmp_path / "bad.wav")


def test_audio_duration_limit_is_not_silent_truncation(silence, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MAX_AUDIO_SECONDS", 1)
    with pytest.raises(ProcessingError, match="AUDIO_DURATION_LIMIT"):
        decode(silence, tmp_path / "long.wav")
    assert not (tmp_path / "long.wav").exists()


@pytest.mark.asr
def test_real_silence_asr(silence):
    if not (Path(config.WHISPER_MODEL) / "model.bin").is_file():
        pytest.skip("Install ASR model separately with scripts/download_model.py")
    assert transcribe_audio(silence) == []


def word_error_rate(reference, hypothesis):
    a = re.findall(r"\w+", reference.lower())
    b = re.findall(r"\w+", hypothesis.lower())
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        nxt = [i]
        for j, y in enumerate(b, 1):
            nxt.append(min(nxt[-1] + 1, row[j] + 1, row[j - 1] + (x != y)))
        row = nxt
    return row[-1] / max(1, len(a))


@pytest.mark.samples
@pytest.mark.asr
@pytest.mark.parametrize("language", ["ru", "kk", "mixed"])
def test_real_language_samples(language):
    root = Path(__file__).resolve().parents[1] / "samples"
    path = root / (language + ".wav")
    reference = root / (language + ".txt")
    if not path.is_file() or not reference.is_file():
        pytest.skip(
            f"Provide consented {language}.wav and {language}.txt reference; text fixtures are not ASR tests"
        )
    if not (Path(config.WHISPER_MODEL) / "model.bin").is_file():
        pytest.skip("ASR model not installed")
    actual = transcribe_audio(path)
    wer = word_error_rate(
        reference.read_text(encoding="utf-8"), " ".join(s.text for s in actual)
    )
    print(f"{language}: WER={wer:.3f}, segments={len(actual)}")
    assert actual and wer <= float(os.getenv("ASR_MAX_WER", "0.35"))
