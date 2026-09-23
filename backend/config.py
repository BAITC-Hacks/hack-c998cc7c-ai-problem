"""Server-only configuration. Processing never downloads models."""
import os
from pathlib import Path
from dotenv import load_dotenv
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / 'backend' / '.env')
DATA_DIR = Path(os.getenv('DATA_DIR', str(ROOT / 'data'))).resolve()
UPLOAD_DIR = DATA_DIR / 'uploads'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = str(DATA_DIR / 'khattama.db')
WHISPER_MODEL = os.getenv('WHISPER_MODEL', str(ROOT / 'backend/models/small'))
LLM_LOCAL_URL = os.getenv('LLM_LOCAL_URL', 'http://127.0.0.1:8080/v1')
LLM_LOCAL_MODEL = os.getenv('LLM_LOCAL_MODEL', 'local-model')
LLM_HYBRID_URL = os.getenv('LLM_HYBRID_URL', '')
LLM_HYBRID_MODEL = os.getenv('LLM_HYBRID_MODEL', '')
LLM_API_KEY = os.getenv('LLM_API_KEY', '')
MAX_UPLOAD_BYTES = int(os.getenv('MAX_UPLOAD_MB', '250')) * 1024 * 1024
MAX_AUDIO_SECONDS = int(os.getenv('MAX_AUDIO_SECONDS', '14400'))
from shutil import which
def ffmpeg_binary():
    if os.getenv('FFMPEG'):
        return os.environ['FFMPEG']
    if which('ffmpeg'):
        return 'ffmpeg'
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()  # bundled wheel binary, no download
    except (ImportError, RuntimeError):
        return 'ffmpeg'
FFMPEG = ffmpeg_binary()
PDF_FONT = os.getenv('PDF_FONT', '')
HOST = os.getenv('HOST', '127.0.0.1')
PORT = int(os.getenv('PORT', '8000'))
ALLOWED_EXT = {'.wav', '.mp3', '.mp4'}
