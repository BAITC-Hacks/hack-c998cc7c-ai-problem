import os

# ============================================================
#  Хаттама AI — общие настройки (backend/config.py)
#  Значения переопределяются переменными окружения / .env
# ============================================================

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(ROOT, "data"))
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
OUTPUT_DIR = os.path.join(DATA_DIR, "outputs")
DB_PATH = os.environ.get("DB_PATH", os.path.join(DATA_DIR, "khattama.db"))

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- Распознавание речи (локально, без облака) ---
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE = os.environ.get("WHISPER_COMPUTE", "int8")
WHISPER_LANGUAGE = os.environ.get("WHISPER_LANGUAGE", "") or None  # None = авто
VAD_FILTER = os.environ.get("VAD_FILTER", "true").lower() == "true"
BEAM_SIZE = int(os.environ.get("BEAM_SIZE", "5"))

# --- LLM: OpenAI → NVIDIA NIM → офлайн-fallback ---
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

NVIDIA_NIM_API_KEY = os.environ.get("NVIDIA_NIM_API_KEY", "").strip()
NVIDIA_NIM_BASE_URL = os.environ.get("NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
NVIDIA_NIM_MODEL = os.environ.get("NVIDIA_NIM_MODEL", "meta/llama-3.3-70b-instruct")

# Разрешённые расширения загрузки
ALLOWED_EXT = {".mp3", ".wav", ".m4a", ".mp4", ".ogg", ".flac", ".webm", ".aac"}

# Порог паузы (сек) для склейки смежных сегментов в одну реплику (диаризация)
TURN_GAP = float(os.environ.get("TURN_GAP", "1.2"))
# Минимальная длительность поручения-фразы при офлайн-извлечении
MIN_TASK_LEN = int(os.environ.get("MIN_TASK_LEN", "18"))