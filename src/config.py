"""
Configuración central y utilidades para el Pipeline de Noticias AdSense.
"""
import os
import sys
import json
import shutil
from pathlib import Path

# Resolver directorios base del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
ASSETS_DIR = BASE_DIR / "assets"
OUTPUT_DIR = BASE_DIR / "output"
CONFIG_FILE = BASE_DIR / "config.json"

# Cargar variables de entorno simples desde .env si existe
env_path = BASE_DIR / ".env"
if env_path.exists():
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())

# Cargar config.json
DEFAULT_CONFIG = {
    "video": {
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "card_max_width": 960,
        "zoom_effect": True,
        "bg_blur_sigma": 20
    },
    "tts": {
        "voice": os.getenv("VOICE_NAME", "es-MX-DaliaNeural"),
        "rate": os.getenv("VOICE_RATE", "+0%"),
        "pitch": os.getenv("VOICE_PITCH", "+0Hz")
    },
    "subtitles": {
        "whisper_model": "base",
        "whisper_device": "cpu",
        "font_name": "Arial",
        "font_size": 76,
        "primary_color": "&H00FFFFFF",
        "karaoke_color": "&H0000FFFF",
        "outline_color": "&H00000000",
        "outline_width": 4,
        "shadow_depth": 2,
        "margin_v": 450
    },
    "adsense_compliance": {
        "min_editorial_words": 80,
        "require_critical_analysis": True,
        "require_human_checkpoint": True
    }
}

CONFIG = DEFAULT_CONFIG.copy()
if CONFIG_FILE.exists():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)
            CONFIG.update(loaded)
    except Exception as e:
        print(f"[Aviso] No se pudo leer {CONFIG_FILE}, usando valores por defecto: {e}")

def get_ffmpeg_path() -> str:
    """
    Encuentra el ejecutable FFmpeg disponible en el sistema.
    Primero busca en el PATH del sistema; si no está, utiliza el binario de imageio_ffmpeg.
    """
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise RuntimeError(
            "FFmpeg no está instalado en el PATH ni disponible vía imageio-ffmpeg. "
            "Ejecuta: pip install imageio-ffmpeg"
        )

# Fix de compatibilidad para PyAV reciente con faster-whisper (evita crash por metadata_errors)
def apply_faster_whisper_compat_patch():
    try:
        import av
        if hasattr(av, "open"):
            _orig_open = av.open
            def _patched_open(*args, **kwargs):
                kwargs.pop("metadata_errors", None)
                return _orig_open(*args, **kwargs)
            av.open = _patched_open
    except ImportError:
        pass

apply_faster_whisper_compat_patch()
