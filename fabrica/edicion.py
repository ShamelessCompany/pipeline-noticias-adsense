"""
Mide cómo editan los canales que funcionan: cortes por minuto, largo medio de plano, golpes de sonido
y (con Gemini) qué tipo de imagen hay en cada corte: B-roll, gráfico con texto, foto enmarcada, mapa…

No se guarda nada de esos videos: se bajan a 360p, se miden y se borran. Lo que queda es la receta
(números y proporciones) que el Director de montaje usa para editar con material propio y libre.
"""
import re
import shutil
import statistics
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from fabrica import llm, media
from src.config import get_ffmpeg_path

TIPOS_PLANO = ["persona_hablando", "broll", "grafico_texto", "imagen_enmarcada", "captura", "mapa", "meme", "otro"]

SISTEMA_PLANOS = f"""Eres analista de edición de video. Te paso fotogramas tomados justo después de cada corte
de un video de YouTube, en orden. Para cada uno dime qué tipo de plano es: {", ".join(TIPOS_PLANO)}.
"grafico_texto" = cifras, palabras o rótulos sobreimpresos además de los subtítulos.
"imagen_enmarcada" = foto o recorte pequeño encima del fondo. Ignora los subtítulos normales.
Responde SOLO JSON: {{"planos": [{{"tipo": "...", "texto_extra": true/false, "zoom": true/false}}]}}"""


def cortes(video: str, umbral: float = 0.3) -> List[float]:
    """Segundos en que cambia el plano (detección de escena de FFmpeg)."""
    cmd = [get_ffmpeg_path(), "-hide_banner", "-i", str(video), "-an",
           "-vf", f"scale=320:-2,select='gt(scene,{umbral})',showinfo", "-f", "null", "-"]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    tiempos = [float(m) for m in re.findall(r"pts_time:([0-9.]+)", res.stderr)]
    # Dos cortes a menos de 0.3 s suelen ser una transición, no dos planos
    out: List[float] = []
    for t in tiempos:
        if not out or t - out[-1] > 0.3:
            out.append(t)
    return out


def golpes_audio(video: str) -> int:
    """Subidas bruscas de volumen (whoosh, impactos, pops) en ventanas de 50 ms."""
    if not media.tiene_audio(video):
        return 0
    e = media.energia_audio(video, ventana=0.05)
    golpes, ultimo = 0, -100
    for i in range(20, len(e)):
        previo = statistics.median(e[i - 20:i])
        if e[i] - previo > 12 and e[i] > -35 and i - ultimo > 10:
            golpes += 1
            ultimo = i
    return golpes


def fotogramas(video: str, tiempos: List[float], carpeta: Path, n: int = 12) -> List[str]:
    if not tiempos:
        return []
    paso = max(1, len(tiempos) // n)
    rutas = []
    for k, t in enumerate(tiempos[::paso][:n]):
        dst = carpeta / f"corte_{k:02d}.jpg"
        try:
            media._ff("-ss", f"{t + 0.3:.2f}", "-i", str(video), "-frames:v", "1", "-vf", "scale=360:-2", "-q:v", "5", str(dst))
            rutas.append(str(dst))
        except Exception:
            continue
    return rutas


def clasificar(imagenes: List[str]) -> Optional[Dict[str, float]]:
    r = llm.ver_imagenes(f"Son {len(imagenes)} fotogramas.", imagenes, SISTEMA_PLANOS)
    planos = r.get("planos") if isinstance(r, dict) else None
    if not planos:
        return None
    n = len(planos)
    prop = {t: round(sum(1 for p in planos if p.get("tipo") == t) / n, 2) for t in TIPOS_PLANO}
    prop["texto_extra"] = round(sum(1 for p in planos if p.get("texto_extra")) / n, 2)
    prop["zoom"] = round(sum(1 for p in planos if p.get("zoom")) / n, 2)
    return prop


def medir(video: str, carpeta: Path, con_vision: bool = True) -> Dict:
    dur = media.duracion(video)
    t = cortes(video)
    planos = [b - a for a, b in zip([0.0] + t, t + [dur])]
    m = {"duracion": round(dur, 1), "cortes": len(t),
         "cortes_por_min": round(len(t) * 60 / dur, 1) if dur else 0,
         "plano_medio_s": round(statistics.median(planos), 2) if planos else dur,
         "golpes_por_min": round(golpes_audio(video) * 60 / dur, 1) if dur else 0}
    if con_vision:
        m["planos"] = clasificar(fotogramas(video, t, carpeta))
    return m


def analizar_url(url: str, carpeta: Path, max_seg: float = 240) -> Dict:
    """Baja a 360p como mucho los primeros max_seg segundos, mide y borra."""
    from fabrica import fuentes
    carpeta.mkdir(parents=True, exist_ok=True)
    try:
        video = fuentes.descargar(url, carpeta / "ref", max_alto=360, inicio=0, fin=max_seg)
        m = medir(str(video), carpeta)
        m["url"] = url
        return m
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)


def receta(muestras: List[Dict], formato: str) -> Dict:
    """Convierte las mediciones de varios videos en la receta que usa el Director de montaje."""
    from fabrica.montaje import RECETAS
    r = dict(RECETAS[formato])
    if not muestras:
        return r

    def med(clave):
        vals = [m[clave] for m in muestras if m.get(clave) is not None]
        return statistics.median(vals) if vals else None

    plano = med("plano_medio_s")
    if plano:
        r["plano_medio_s"] = round(min(8.0, max(1.2, plano)), 2)
    cpm = med("cortes_por_min")
    gpm = med("golpes_por_min")
    if cpm and gpm is not None:
        r["sfx_cortes"] = round(min(1.0, gpm / cpm), 2) if cpm else r["sfx_cortes"]
    vision = [m["planos"] for m in muestras if m.get("planos")]
    if vision:
        def prop(k):
            return statistics.mean(v.get(k, 0) for v in vision)
        graficos = prop("grafico_texto") + prop("texto_extra") / 2
        r["insertos_por_min"] = round(max(2, min(20, (cpm or 10) * (graficos + prop("imagen_enmarcada")))), 1)
        r["palabras_clave"] = prop("texto_extra") >= 0.2
        r["imagenes"] = prop("imagen_enmarcada") + prop("captura") + prop("mapa") >= 0.08
        r["zoom_punch"] = prop("zoom") >= 0.1
        r["tipos_plano"] = {k: round(prop(k), 2) for k in TIPOS_PLANO}
    r["cortes_por_min"] = cpm
    r["muestras"] = len(muestras)
    r["origen"] = "aprendida de los canales de referencia"
    return r
