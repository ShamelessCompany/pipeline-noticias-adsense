"""
Rutas, variables de entorno y archivos de configuración editables desde el panel.
Todo vive en data/ como JSON para que se pueda tocar a mano o desde la interfaz.
"""
import os
import json
import copy
import threading
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
ESTILOS_DIR = DATA_DIR / "estilos"
TRABAJOS_DIR = BASE_DIR / "output" / "trabajos"
CACHE_DIR = BASE_DIR / "output" / "cache"
DB_PATH = DATA_DIR / "fabrica.db"

for d in (DATA_DIR, ESTILOS_DIR, TRABAJOS_DIR, CACHE_DIR):
    d.mkdir(parents=True, exist_ok=True)

# Cargar .env sin dependencias externas (mismo criterio que src/config.py)
_env = BASE_DIR / ".env"
if _env.exists():
    for linea in _env.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            k, v = linea.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

_lock = threading.Lock()

AJUSTES_DEFECTO = {
    "piloto_automatico": False,          # el trabajador procesa la cola solo
    "aprobacion_manual": True,           # un humano aprueba antes de publicar (recomendado para YPP)
    "umbral_auto_aprobacion": 85,        # puntaje mínimo si aprobacion_manual = False
    "modo_publicacion": "simulado",      # simulado | real (requiere client_secrets.json)
    "privacidad_publicacion": "private",
    "intervalo_ciclo_min": 60,           # cada cuánto el explorador busca material nuevo
    "max_trabajos_por_ciclo": 3,
    "whisper_modelo": "base",
    "dias_retencion": 7,                 # días que se guardan los archivos pesados de lo ya publicado
    "llm": {
        "orden": ["gemini", "opencode", "ollama", "local"],
        "gemini": {"modelo": "gemini-2.5-flash", "api_key_env": "GEMINI_API_KEY"},
        "opencode": {
            "base_url": "https://opencode.ai/zen/v1",
            "modelo": "",
            "api_key_env": "OPENCODE_API_KEY"
        },
        "ollama": {"base_url": "http://localhost:11434/v1", "modelo": "llama3.1"},
        "temperatura": 0.8
    },
    "broll": {
        "pexels_key_env": "PEXELS_API_KEY",
        "pixabay_key_env": "PIXABAY_API_KEY",
        "usar_wikimedia": True
    }
}


def _leer_json(path: Path, defecto):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[Ajustes] No se pudo leer {path.name}: {e}")
    return copy.deepcopy(defecto)


def _escribir_json(path: Path, data) -> None:
    with _lock:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)


def _fusionar(base: dict, nuevo: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (nuevo or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _fusionar(out[k], v)
        else:
            out[k] = v
    return out


def cargar_ajustes() -> dict:
    return _fusionar(AJUSTES_DEFECTO, _leer_json(DATA_DIR / "ajustes.json", {}))


def guardar_ajustes(data: dict) -> dict:
    final = _fusionar(cargar_ajustes(), data)
    _escribir_json(DATA_DIR / "ajustes.json", final)
    return final


def cargar_nichos() -> list:
    return _leer_json(DATA_DIR / "nichos.json", [])


def guardar_nichos(nichos: list) -> None:
    _escribir_json(DATA_DIR / "nichos.json", nichos)


def obtener_nicho(nicho_id: str) -> dict:
    for n in cargar_nichos():
        if n.get("id") == nicho_id:
            return n
    nichos = cargar_nichos()
    return nichos[0] if nichos else {"id": "general", "nombre": "General", "formato": "short"}


def cargar_fuentes() -> list:
    return _leer_json(DATA_DIR / "fuentes.json", [])


def guardar_fuentes(fuentes: list) -> None:
    _escribir_json(DATA_DIR / "fuentes.json", fuentes)


def cargar_estilo(nicho_id: str) -> dict:
    return _leer_json(ESTILOS_DIR / f"{nicho_id}.json", {})


def guardar_estilo(nicho_id: str, estilo: dict) -> None:
    _escribir_json(ESTILOS_DIR / f"{nicho_id}.json", estilo)


FORMATOS = {
    "short": {"ancho": 1080, "alto": 1920, "seg_min": 20, "seg_max": 58, "palabras": (90, 140)},
    "largo": {"ancho": 1920, "alto": 1080, "seg_min": 180, "seg_max": 720, "palabras": (700, 1400)},
}
