"""Local CPU int8 ASR. No downloads or per-segment language claims."""
from pathlib import Path
import config
from llm_client import ProcessingError
from schemas import Segment

_model = None

def transcribe_audio(path):
    global _model
    model_path = Path(config.WHISPER_MODEL)
    if not model_path.is_dir() or not (model_path / 'model.bin').is_file():
        raise ProcessingError('ASR_MODEL_MISSING: run scripts/download_model.py separately and set WHISPER_MODEL in backend/.env')
    try:
        from faster_whisper import WhisperModel
        if _model is None:
            _model = WhisperModel(str(model_path.resolve()),device='cpu',compute_type='int8',local_files_only=True)
        segments, _ = _model.transcribe(str(path), task='transcribe',vad_filter=True,beam_size=5)
        return [Segment(id=f's{i}',start=float(s.start),end=float(s.end),text=s.text.strip())
                for i,s in enumerate(segments) if s.text.strip()]
    except ProcessingError:
        raise
    except Exception:
        raise ProcessingError('ASR_FAILED: check local model files and faster-whisper CPU runtime') from None
