"""
Música propia: importa los temas del Motor de Música (P4, repo motor-musica-content-id)
a assets/musica/<nicho>/, que es donde el Editor busca la pista de fondo.

Solo entran temas con content_id_certified y sin sample packs. Los WAV se pasan a MP3
para que la carpeta pese poco y viaje con subir_codigo.ps1. El manifiesto guarda el ISRC
de cada archivo para que el Empaquetador lo acredite en la descripción.
"""
import json
from pathlib import Path
from typing import Dict, List, Optional

from fabrica.ajustes import BASE_DIR

MUSICA_DIR = BASE_DIR / "assets" / "musica"
MANIFIESTO = MUSICA_DIR / "catalogo_propio.json"
ORIGEN_DEFECTO = BASE_DIR.parent / "motor-musica-content-id"

# Qué géneros del motor encajan con cada nicho. Los medleys de DJ no entran: repiten temas ya importados.
GENERO_A_NICHOS = {
    "lofi_chill": ["curiosidades"],
    "synthwave": ["curiosidades", "tecnologia"],
    "epic_cinematic": ["historia", "misterios"],
    "dark_trap": ["misterios", "clips_streams"],
    "boom_bap": ["clips_streams", "curiosidades"],
    "hard_rock": ["clips_streams"],
}


def _cargar_manifiesto() -> Dict[str, Dict]:
    if MANIFIESTO.exists():
        return json.loads(MANIFIESTO.read_text(encoding="utf-8"))
    return {}


def importar(origen: Optional[Path] = None, bitrate: str = "192k") -> Dict[str, List[str]]:
    """Convierte y reparte los temas del catálogo de P4. Devuelve {nicho: [archivos nuevos]}."""
    from fabrica.media import _ff

    origen = Path(origen or ORIGEN_DEFECTO)
    catalogo = origen / "output" / "metadata" / "catalog_content_id.json"
    if not catalogo.exists():
        raise FileNotFoundError(f"No encuentro el catálogo del motor de música en {catalogo}")
    manifiesto = _cargar_manifiesto()
    nuevos: Dict[str, List[str]] = {}
    for tema in json.loads(catalogo.read_text(encoding="utf-8")):
        if not tema.get("content_id_certified") or tema.get("sample_packs_used"):
            continue
        wav = origen / "output" / "audio" / tema["audio_filename"]
        if not wav.exists():
            continue
        nombre = f"{tema['isrc']}.mp3"
        for nicho in GENERO_A_NICHOS.get(tema.get("genre", ""), []):
            destino = MUSICA_DIR / nicho / nombre
            if not destino.exists():
                destino.parent.mkdir(parents=True, exist_ok=True)
                _ff("-i", str(wav), "-vn", "-c:a", "libmp3lame", "-b:a", bitrate, str(destino))
                nuevos.setdefault(nicho, []).append(nombre)
        manifiesto[nombre] = {k: tema.get(k) for k in ("isrc", "title", "artist", "genre", "bpm", "duration_sec")}
    MUSICA_DIR.mkdir(parents=True, exist_ok=True)
    MANIFIESTO.write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding="utf-8")
    return nuevos


def credito(ruta: Optional[str]) -> str:
    """Línea de créditos para una pista elegida, o '' si no es música propia."""
    if not ruta:
        return ""
    tema = _cargar_manifiesto().get(Path(ruta).name)
    if not tema:
        return ""
    return f"Música: «{tema['title']}» — {tema['artist']} (ISRC {tema['isrc']})"
