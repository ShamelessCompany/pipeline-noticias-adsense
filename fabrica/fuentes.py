"""
Acceso a YouTube y Twitch con yt-dlp (gratis, sin API key):
listar videos recientes o populares de un canal, bajar un video o un tramo,
y leer subtítulos/transcripciones ya publicados para no gastar CPU en Whisper.
"""
import os
import re
import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from fabrica.ajustes import CACHE_DIR


def _ytdlp(*args: str, timeout: int = 600) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "-m", "yt_dlp", "--no-warnings", "--ignore-config"]
    # En una VPS YouTube suele pedir "confirma que no eres un bot": unas cookies exportadas lo evitan
    cookies = os.getenv("YTDLP_COOKIES", "")
    if cookies and Path(cookies).exists():
        cmd += ["--cookies", cookies]
    cmd += shlex.split(os.getenv("YTDLP_EXTRA", "")) + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def plataforma(url: str) -> str:
    if "twitch.tv" in url:
        return "twitch"
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    return "otra"


def listar_canal(url_canal: str, limite: int = 10, populares: bool = False) -> List[Dict]:
    """Devuelve [{url, titulo, vistas, duracion}] de un canal o lista sin descargar nada."""
    url = url_canal.rstrip("/")
    if plataforma(url) == "youtube" and not re.search(r"/(videos|streams|shorts|playlist)", url) and "watch?" not in url:
        url += "/videos"
    args = ["--flat-playlist", "-J", "--playlist-end", str(limite * (4 if populares else 1))]
    res = _ytdlp(*args, url, timeout=180)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip()[-400:] or "yt-dlp no pudo leer el canal")
    data = json.loads(res.stdout)
    items = []
    for e in data.get("entries") or []:
        if not e:
            continue
        vurl = e.get("url") or e.get("webpage_url") or ""
        if vurl and not vurl.startswith("http"):
            vurl = f"https://www.youtube.com/watch?v={vurl}"
        items.append({
            "url": vurl,
            "titulo": e.get("title") or "",
            "vistas": int(e.get("view_count") or 0),
            "duracion": float(e.get("duration") or 0),
        })
    if populares:
        items.sort(key=lambda x: x["vistas"], reverse=True)
    return items[:limite]


def info_video(url: str) -> Dict:
    res = _ytdlp("-J", "--skip-download", url, timeout=120)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip()[-400:])
    d = json.loads(res.stdout)
    return {
        "titulo": d.get("title", ""),
        "canal": d.get("uploader") or d.get("channel") or "",
        "duracion": float(d.get("duration") or 0),
        "vistas": int(d.get("view_count") or 0),
        "descripcion": (d.get("description") or "")[:2000],
        "tags": d.get("tags") or [],
        "licencia": d.get("license") or "",
        "url": d.get("webpage_url") or url,
    }


def descargar(url: str, destino: Path, max_alto: int = 1080,
              inicio: Optional[float] = None, fin: Optional[float] = None) -> Path:
    """Baja el video (o solo un tramo) a destino.mp4."""
    destino = Path(destino).with_suffix("")
    destino.parent.mkdir(parents=True, exist_ok=True)
    args = ["-f", f"bv*[height<={max_alto}]+ba/b[height<={max_alto}]/b",
            "--merge-output-format", "mp4", "-o", str(destino) + ".%(ext)s"]
    if inicio is not None and fin is not None:
        args += ["--download-sections", f"*{inicio:.2f}-{fin:.2f}", "--force-keyframes-at-cuts"]
    res = _ytdlp(*args, url, timeout=3600)
    final = destino.with_suffix(".mp4")
    if res.returncode != 0 or not final.exists():
        candidatos = list(destino.parent.glob(destino.name + ".*"))
        if candidatos:
            return candidatos[0]
        raise RuntimeError(res.stderr.strip()[-600:] or "Falló la descarga")
    return final


def _parse_vtt(texto: str) -> List[Dict]:
    """Convierte un .vtt en segmentos [{inicio, fin, texto}] quitando duplicados de auto-subs."""
    segs, previo = [], ""
    bloques = re.split(r"\n\s*\n", texto)
    for b in bloques:
        m = re.search(r"(\d+):(\d\d):(\d\d)[.,](\d+)\s+-->\s+(\d+):(\d\d):(\d\d)[.,](\d+)", b)
        if not m:
            continue
        g = list(map(int, m.groups()))
        ini = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        fin = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        lineas = b[m.end():].strip().splitlines()
        txt = " ".join(re.sub(r"<[^>]+>", "", l).strip() for l in lineas).strip()
        if not txt or txt == previo:
            continue
        if previo and txt.startswith(previo):
            txt = txt[len(previo):].strip()
        previo = " ".join(re.sub(r"<[^>]+>", "", l).strip() for l in lineas).strip()
        if txt:
            segs.append({"inicio": ini, "fin": fin, "texto": txt})
    return segs


def transcripcion_publicada(url: str, idiomas: str = "es.*,en.*") -> Optional[List[Dict]]:
    """Lee subtítulos (manuales o automáticos) ya publicados. None si no hay."""
    base = CACHE_DIR / ("subs_" + re.sub(r"\W+", "_", url)[-60:])
    _ytdlp("--skip-download", "--write-subs", "--write-auto-subs", "--sub-langs", idiomas,
                 "--sub-format", "vtt", "-o", str(base) + ".%(ext)s", url, timeout=180)
    archivos = sorted(base.parent.glob(base.name + "*.vtt"), key=lambda p: (".es" not in p.name, p.name))
    if not archivos:
        return None
    segs = _parse_vtt(archivos[0].read_text(encoding="utf-8", errors="ignore"))
    return segs or None


def texto_plano(segmentos: List[Dict]) -> str:
    return " ".join(s["texto"] for s in segmentos)
