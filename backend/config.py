"""Server-only configuration. Processing never downloads models."""

import os
import ipaddress
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")
DATA_DIR = Path(os.getenv("DATA_DIR", str(ROOT / "data"))).resolve()
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = str(DATA_DIR / "khattama.db")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", str(ROOT / "backend/models/small"))
LLM_LOCAL_URL = os.getenv("LLM_LOCAL_URL", "http://127.0.0.1:8080/v1")
LLM_LOCAL_MODEL = os.getenv("LLM_LOCAL_MODEL", "local-model")
LLM_HYBRID_URL = os.getenv("LLM_HYBRID_URL", "")
LLM_HYBRID_MODEL = os.getenv("LLM_HYBRID_MODEL", "")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
DEFAULT_MODE = os.getenv("DEFAULT_MODE", "HYBRID")
DEFAULT_ASR_MODE = os.getenv("DEFAULT_ASR_MODE", "API")
ASR_API_URL = os.getenv("ASR_API_URL", "")
ASR_API_MODEL = os.getenv("ASR_API_MODEL", "")
ASR_API_KEY = os.getenv("ASR_API_KEY", "")
# PCM mono 16 kHz: a 600-second part is about 19.2 MB.
ASR_CHUNK_SECONDS = int(os.getenv("ASR_CHUNK_SECONDS", "600"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "250")) * 1024 * 1024
MAX_AUDIO_SECONDS = int(os.getenv("MAX_AUDIO_SECONDS", "14400"))
from shutil import which


def ffmpeg_binary():
    if os.getenv("FFMPEG"):
        return os.environ["FFMPEG"]
    if which("ffmpeg"):
        return "ffmpeg"
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()  # bundled wheel binary, no download
    except (ImportError, RuntimeError):
        return "ffmpeg"


FFMPEG = ffmpeg_binary()
PDF_FONT = os.getenv("PDF_FONT", "")
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
ALLOWED_EXT = {".wav", ".mp3", ".mp4"}
PUBLIC_MODE = os.getenv("PUBLIC_MODE", "false").lower() == "true"
APP_AUTH_USER = os.getenv("APP_AUTH_USER", "demo")
APP_AUTH_PASSWORD = os.getenv("APP_AUTH_PASSWORD", "")
ALLOWED_HOSTS = [
    host.strip() for host in os.getenv(
        "ALLOWED_HOSTS", "localhost,127.0.0.1,[::1],testserver"
    ).split(",") if host.strip()
]


def validate_deployment():
    if not PUBLIC_MODE:
        try:
            loopback = HOST == 'localhost' or ipaddress.ip_address(HOST).is_loopback
        except ValueError:
            loopback = False
        if not loopback:
            raise ValueError('Local mode requires a loopback HOST (127.0.0.1 or ::1)')
    if DEFAULT_MODE not in {"LOCAL", "HYBRID", "RULES"} or DEFAULT_ASR_MODE not in {"LOCAL", "API"}:
        raise ValueError("Invalid DEFAULT_MODE or DEFAULT_ASR_MODE")
    if not 1 <= ASR_CHUNK_SECONDS <= 600:
        raise ValueError("ASR_CHUNK_SECONDS must be between 1 and 600")
    if PUBLIC_MODE and len(APP_AUTH_PASSWORD) < 16:
        raise ValueError("PUBLIC_MODE requires APP_AUTH_PASSWORD of at least 16 characters")
    if PUBLIC_MODE and (not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS):
        raise ValueError("PUBLIC_MODE requires explicit ALLOWED_HOSTS")
