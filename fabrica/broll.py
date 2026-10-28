"""
Material visual de apoyo (B-roll) gratuito y con licencia que permite uso comercial.
Orden de búsqueda:
1. La biblioteca local (lo ya descargado o subido; se prefiere lo menos usado)
2. Pexels (videos, clave gratis en PEXELS_API_KEY)
3. Pixabay (videos, clave gratis en PIXABAY_API_KEY)
4. Openverse (imágenes CC0/CC BY/CC BY-SA, sin clave)
5. Wikimedia Commons (imágenes libres, sin clave)
6. NASA Image Library (dominio público, sin clave; útil en ciencia, espacio, Tierra)
7. Tarjetas generadas en local con Pillow (siempre disponibles)
Todo lo que se descarga queda en la biblioteca con su licencia y su crédito.
"""
import os
import random
import re
import textwrap
from pathlib import Path
from typing import Dict, List, Optional

import requests

from fabrica import biblioteca
from fabrica.ajustes import cargar_ajustes
from fabrica.biblioteca import BIBLIOTECA_DIR

UA = {"User-Agent": "FabricaContenido/1.0 (uso personal)"}

PALETAS = [
    ((12, 16, 28), (56, 189, 248)), ((24, 12, 28), (244, 114, 182)), ((10, 24, 18), (52, 211, 153)),
    ((28, 20, 8), (251, 191, 36)), ((20, 14, 34), (167, 139, 250)), ((30, 10, 10), (248, 113, 113)),
]


def _bajar(url: str, dst: Path) -> Optional[Path]:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and dst.stat().st_size > 0:
        return dst
    try:
        with requests.get(url, headers=UA, timeout=60, stream=True) as r:
            r.raise_for_status()
            with open(dst, "wb") as f:
                for chunk in r.iter_content(1 << 16):
                    f.write(chunk)
        return dst
    except Exception as e:
        print(f"[B-roll] No se pudo bajar {url[:80]}: {e}")
        return None


def _registrar(v: Dict, consulta: str, nicho: str = "") -> Optional[Dict]:
    """Guarda en la biblioteca lo descargado. Devuelve None si la licencia no sirve."""
    rid = biblioteca.agregar(v["ruta"], v["tipo"], v["licencia"], v.get("credito", ""), origen=v["fuente"],
                             url_origen=v.get("origen", ""), etiquetas=f"{consulta} {v.get('etiquetas', '')}",
                             descripcion=v.get("descripcion", ""), nicho=nicho)
    if not rid:
        return None
    v["recurso_id"] = rid
    return v


def _pexels(q: str, vertical: bool) -> Optional[Dict]:
    key = os.getenv(cargar_ajustes()["broll"]["pexels_key_env"], "")
    if not key:
        return None
    try:
        r = requests.get("https://api.pexels.com/videos/search", headers={"Authorization": key}, timeout=20,
                         params={"query": q, "per_page": 8, "orientation": "portrait" if vertical else "landscape"})
        videos = r.json().get("videos", [])
        if not videos:
            return None
        v = random.choice(videos[:5])
        archivos = sorted([f for f in v["video_files"] if f.get("height")], key=lambda f: abs(f["height"] - 1080))
        dst = BIBLIOTECA_DIR / "pexels" / f"pexels_{v['id']}.mp4"
        if _bajar(archivos[0]["link"], dst):
            etiquetas = re.sub(r"[-/]", " ", v.get("url", "").rstrip("/").split("/")[-1])
            return {"tipo": "video", "ruta": str(dst), "credito": f"Pexels: {v['user']['name']}", "origen": v["url"],
                    "licencia": "pexels", "fuente": "pexels", "etiquetas": etiquetas}
    except Exception as e:
        print(f"[B-roll] Pexels: {e}")
    return None


def _pixabay(q: str, vertical: bool) -> Optional[Dict]:
    key = os.getenv(cargar_ajustes()["broll"]["pixabay_key_env"], "")
    if not key:
        return None
    try:
        r = requests.get("https://pixabay.com/api/videos/", timeout=20,
                         params={"key": key, "q": q, "per_page": 8, "safesearch": "true"})
        hits = r.json().get("hits", [])
        if not hits:
            return None
        h = random.choice(hits[:5])
        url = (h["videos"].get("medium") or h["videos"].get("small"))["url"]
        dst = BIBLIOTECA_DIR / "pixabay" / f"pixabay_{h['id']}.mp4"
        if _bajar(url, dst):
            return {"tipo": "video", "ruta": str(dst), "credito": f"Pixabay: {h['user']}", "origen": h["pageURL"],
                    "licencia": "pixabay", "fuente": "pixabay", "etiquetas": h.get("tags", "")}
    except Exception as e:
        print(f"[B-roll] Pixabay: {e}")
    return None


def _openverse(q: str) -> Optional[Dict]:
    try:
        r = requests.get("https://api.openverse.org/v1/images/", headers=UA, timeout=20, params={
            "q": q, "license_type": "commercial", "page_size": 8, "mature": "false"})
        res = [x for x in r.json().get("results", []) if biblioteca.normalizar_licencia(x.get("license", ""))]
        if not res:
            return None
        x = random.choice(res[:5])
        ext = (Path(x["url"]).suffix.split("?")[0] or ".jpg")[:5]
        dst = BIBLIOTECA_DIR / "openverse" / f"ov_{x['id']}{ext}"
        if _bajar(x["url"], dst):
            autor = x.get("creator") or "autor desconocido"
            lic = f"cc-{x['license']}" if x["license"] not in ("cc0", "pdm") else x["license"]
            return {"tipo": "imagen", "ruta": str(dst), "credito": f"{x.get('title', '')[:60]} de {autor} vía Openverse",
                    "origen": x.get("foreign_landing_url", ""), "licencia": lic, "fuente": "openverse",
                    "etiquetas": " ".join(t.get("name", "") for t in (x.get("tags") or [])[:12]),
                    "descripcion": x.get("title", "")}
    except Exception as e:
        print(f"[B-roll] Openverse: {e}")
    return None


def _wikimedia(q: str) -> Optional[Dict]:
    if not cargar_ajustes()["broll"].get("usar_wikimedia", True):
        return None
    try:
        r = requests.get("https://commons.wikimedia.org/w/api.php", headers=UA, timeout=20, params={
            "action": "query", "generator": "search", "gsrsearch": f"filetype:bitmap {q}", "gsrnamespace": 6,
            "gsrlimit": 8, "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": 1600, "format": "json"})
        paginas = list((r.json().get("query") or {}).get("pages", {}).values())
        validas = []
        for p in paginas:
            meta = p["imageinfo"][0].get("extmetadata", {})
            if biblioteca.normalizar_licencia(meta.get("LicenseShortName", {}).get("value", "")):
                validas.append(p)
        if not validas:
            return None
        p = random.choice(validas[:4])
        info = p["imageinfo"][0]
        meta = info.get("extmetadata", {})
        autor = re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value") or "Wikimedia Commons").strip()[:60]
        licencia = meta.get("LicenseShortName", {}).get("value", "")
        ext = Path(info.get("thumburl") or info["url"]).suffix.split("?")[0] or ".jpg"
        dst = BIBLIOTECA_DIR / "wikimedia" / f"wm_{p['pageid']}{ext}"
        if _bajar(info.get("thumburl") or info["url"], dst):
            desc = re.sub(r"<[^>]+>", "", meta.get("ImageDescription", {}).get("value", ""))[:200]
            return {"tipo": "imagen", "ruta": str(dst), "credito": f"Wikimedia Commons: {autor}",
                    "origen": info.get("descriptionurl", ""), "licencia": licencia, "fuente": "wikimedia",
                    "etiquetas": p.get("title", "").replace("File:", ""), "descripcion": desc}
    except Exception as e:
        print(f"[B-roll] Wikimedia: {e}")
    return None


def _nasa(q: str) -> Optional[Dict]:
    try:
        r = requests.get("https://images-api.nasa.gov/search", headers=UA, timeout=20,
                         params={"q": q, "media_type": "image", "page_size": 8})
        items = r.json().get("collection", {}).get("items", [])
        items = [i for i in items if i.get("links")]
        if not items:
            return None
        it = random.choice(items[:5])
        d = it["data"][0]
        dst = BIBLIOTECA_DIR / "nasa" / f"nasa_{re.sub(r'[^A-Za-z0-9_-]', '', d['nasa_id'])[:60]}.jpg"
        if _bajar(it["links"][0]["href"], dst):
            return {"tipo": "imagen", "ruta": str(dst), "credito": f"NASA: {d.get('center', '')}".strip(": "),
                    "origen": f"https://images.nasa.gov/details/{d['nasa_id']}", "licencia": "nasa", "fuente": "nasa",
                    "etiquetas": " ".join(d.get("keywords", [])[:10]), "descripcion": d.get("title", "")}
    except Exception as e:
        print(f"[B-roll] NASA: {e}")
    return None


FUENTES_VIDEO = {"pexels": _pexels, "pixabay": _pixabay}
FUENTES_IMAGEN = {"openverse": lambda q, v: _openverse(q), "wikimedia": lambda q, v: _wikimedia(q),
                  "nasa": lambda q, v: _nasa(q)}


def buscar_recurso(consulta: str, vertical: bool, preferir: str = "video", nicho: str = "",
                   excluir: Optional[set] = None, fuentes: Optional[List[str]] = None,
                   umbral_biblioteca: float = 0.5) -> Optional[Dict]:
    """
    Busca un recurso para la consulta: primero en la biblioteca y, si no hay nada bueno, en internet.
    preferir: 'video' (B-roll en movimiento) o 'imagen' (foto concreta de algo o alguien).
    """
    excluir = excluir or set()
    tipos = ("video", "imagen") if preferir == "video" else ("imagen", "video")
    locales = biblioteca.buscar(consulta, tipos, n=3, excluir=excluir, nicho=nicho)
    if locales and locales[0]["puntaje"] >= umbral_biblioteca:
        r = locales[0]
        return {"tipo": r["tipo"], "ruta": r["ruta"], "credito": r["credito"], "origen": r["url_origen"],
                "licencia": r["licencia"], "recurso_id": r["id"], "desde": "biblioteca"}
    orden = list(FUENTES_VIDEO.items()) + list(FUENTES_IMAGEN.items()) if preferir == "video" \
        else list(FUENTES_IMAGEN.items()) + list(FUENTES_VIDEO.items())
    for nombre, fn in orden:
        if fuentes and nombre not in fuentes:
            continue
        v = fn(consulta, vertical)
        if v:
            v = _registrar(v, consulta, nicho)
            if v and v["recurso_id"] not in excluir:
                v["desde"] = nombre
                return v
    if locales:
        r = locales[0]
        return {"tipo": r["tipo"], "ruta": r["ruta"], "credito": r["credito"], "origen": r["url_origen"],
                "licencia": r["licencia"], "recurso_id": r["id"], "desde": "biblioteca"}
    return None


def tarjeta(texto: str, dst: Path, ancho: int, alto: int, indice: int = 0, etiqueta: str = "") -> Dict:
    """Tarjeta tipográfica con degradado; siempre funciona sin internet."""
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    fondo, acento = PALETAS[indice % len(PALETAS)]
    img = Image.new("RGB", (ancho, alto), fondo)
    d = ImageDraw.Draw(img)
    for y in range(alto):
        k = y / alto
        d.line([(0, y), (ancho, y)], fill=tuple(int(fondo[c] * (1 - k * 0.5) + acento[c] * k * 0.25) for c in range(3)))
    glow = Image.new("RGB", (ancho, alto), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    r = int(min(ancho, alto) * 0.45)
    cx, cy = int(ancho * (0.25 + 0.5 * (indice % 2))), int(alto * 0.3)
    gd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=tuple(int(c * 0.35) for c in acento))
    img = Image.blend(img, glow.filter(ImageFilter.GaussianBlur(r // 2)), 0.5)
    d = ImageDraw.Draw(img)

    def fuente(tam, negrita=True):
        for nombre in (["arialbd.ttf", "DejaVuSans-Bold.ttf", "Inter-Bold.otf"] if negrita else ["arial.ttf", "DejaVuSans.ttf"]):
            for base in ("", "/usr/share/fonts/truetype/dejavu/", "/usr/share/fonts/opentype/inter/", "C:/Windows/Fonts/"):
                try:
                    return ImageFont.truetype(base + nombre, tam)
                except Exception:
                    continue
        return ImageFont.load_default()

    vertical = alto > ancho
    tam = int(ancho * (0.085 if vertical else 0.05))
    f = fuente(tam)
    lineas = textwrap.wrap(texto, width=16 if vertical else 30)[:5]
    alto_bloque = len(lineas) * int(tam * 1.2)
    y = int(alto * 0.36) - alto_bloque // 2
    if etiqueta:
        fe = fuente(int(tam * 0.42))
        d.rounded_rectangle([int(ancho * 0.08), y - int(tam * 1.1), int(ancho * 0.08) + int(len(etiqueta) * tam * 0.28) + 40,
                             y - int(tam * 0.35)], radius=14, fill=acento)
        d.text((int(ancho * 0.08) + 20, y - int(tam * 1.0)), etiqueta.upper(), font=fe, fill=fondo)
    for linea in lineas:
        d.text((int(ancho * 0.08), y), linea, font=f, fill=(245, 247, 250))
        y += int(tam * 1.2)
    d.rectangle([int(ancho * 0.08), y + 20, int(ancho * 0.08) + int(ancho * 0.18), y + 30], fill=acento)
    img.save(dst, quality=92)
    return {"tipo": "imagen", "ruta": str(dst), "credito": "", "origen": "generado", "zoom": "in" if indice % 2 else "out"}


def buscar_visual(consulta: str, vertical: bool, dst_tarjeta: Path, texto_tarjeta: str,
                  ancho: int, alto: int, indice: int = 0, nicho: str = "", excluir: Optional[set] = None) -> Dict:
    v = buscar_recurso(consulta, vertical, "video", nicho=nicho, excluir=excluir)
    if not v:
        v = tarjeta(texto_tarjeta, dst_tarjeta, ancho, alto, indice)
    v["consulta"] = consulta
    v["zoom"] = "in" if indice % 2 else "out"
    return v
