"""
Revisión automática contra las políticas de monetización de YouTube (YPP) antes de que
un humano vea la pieza. No sustituye la revisión humana: la prepara y deja todo anotado.

Los dos riesgos principales para canales automatizados:
- Contenido reutilizado: material ajeno sin aporte propio significativo.
- Contenido repetitivo / producido en masa: piezas casi idénticas entre sí.
"""
import re
from typing import Dict, List, Optional

from fabrica import estilo
from fabrica.ajustes import cargar_fuentes


def _ngramas(texto: str, n: int = 5) -> set:
    toks = re.findall(r"\w+", texto.lower())
    return {" ".join(toks[i:i + n]) for i in range(max(0, len(toks) - n + 1))}


def solapamiento(texto: str, referencia: str, n: int = 5) -> float:
    """% de 5-gramas del guion que aparecen literalmente en la referencia."""
    a, b = _ngramas(texto, n), _ngramas(referencia, n)
    if not a or not b:
        return 0.0
    return round(len(a & b) / len(a) * 100, 1)


def fuente_permitida(url: str) -> Dict[str, object]:
    for f in cargar_fuentes():
        canal = f.get("url", "").rstrip("/").lower()
        if canal and (url.lower().startswith(canal) or f.get("nombre", "").lower() in url.lower()):
            return {"registrada": True, "permite_clips": bool(f.get("permite_clips")), "fuente": f}
    return {"registrada": False, "permite_clips": False, "fuente": None}


def _item(nombre: str, ok: bool, detalle: str, peso: int, bloqueante: bool = False) -> Dict:
    return {"nombre": nombre, "ok": bool(ok), "detalle": detalle, "peso": peso, "bloqueante": bloqueante}


def revisar_clip(datos: Dict, meta: Dict, url_fuente: str, permiso_manual: bool = False) -> Dict:
    permiso = fuente_permitida(url_fuente)
    ok_permiso = permiso["permite_clips"] or permiso_manual
    dur = float(datos.get("duracion", 0))
    items = [
        _item("Permiso del creador para clips", ok_permiso,
              "Fuente en la lista con permiso" if permiso["permite_clips"] else
              ("Marcado a mano como permitido" if permiso_manual else
               "La fuente no está en Fuentes con 'permite clips'. Sin permiso hay riesgo de reclamo de copyright."),
              30, bloqueante=True),
        _item("Aporte propio visible", bool(datos.get("titulo_overlay")) and bool(datos.get("subtitulos")),
              "Título en pantalla y subtítulos propios", 15),
        _item("Contexto narrado", bool(datos.get("intro_narrada")),
              "Intro con voz propia que explica el momento" if datos.get("intro_narrada") else
              "Sin intro narrada: el clip depende solo del material original", 15),
        _item("Duración adecuada", 15 <= dur <= 180, f"{dur:.0f} s", 10),
        _item("Crédito al creador", any("Fuente" in c or "Clip de" in c for c in [meta.get("descripcion", "")]),
              "Crédito y enlace en la descripción", 15),
        _item("Título no engañoso", _titulo_ok(meta.get("titulo", "")), meta.get("titulo", ""), 15),
    ]
    return _cerrar(items)


def revisar_original(guion: str, referencia: str, meta: Dict, voz_simulada: bool,
                     visuales: List[Dict], min_palabras: int, insertos: Optional[List[Dict]] = None) -> Dict:
    sol = solapamiento(guion, referencia) if referencia else 0.0
    hum = estilo.puntaje_humano(guion)
    propios = sum(1 for v in visuales if v.get("origen") != "generado")
    palabras = len(guion.split())
    items = [
        _item("Guion original (no copiado)", sol < 12, f"{sol}% de frases de 5 palabras coinciden con la referencia",
              30, bloqueante=sol >= 25),
        _item("Extensión del análisis", palabras >= min_palabras, f"{palabras} palabras (mínimo {min_palabras})", 15),
        _item("Escritura humana", hum["puntaje"] >= 70,
              f"Puntaje {hum['puntaje']}/100, variación de frases {hum['variacion_frases']}", 15),
        _item("Voz real generada", not voz_simulada,
              "Voz sintetizada" if not voz_simulada else "Voz simulada (sin internet): regenerar antes de publicar",
              15, bloqueante=voz_simulada),
        _item("Material visual variado", len(visuales) >= 3,
              f"{len(visuales)} tomas, {propios} de bancos libres con crédito", 10),
        _item("Título no engañoso", _titulo_ok(meta.get("titulo", "")), meta.get("titulo", ""), 15),
    ]
    if insertos is not None:
        items.append(licencias_recursos(visuales + insertos))
    return _cerrar(items)


def licencias_recursos(usados: List[Dict]) -> Dict:
    """Todo recurso de terceros tiene que tener licencia de uso comercial y, si la pide, crédito."""
    from fabrica import biblioteca
    malos, sin_credito, n = [], 0, 0
    for u in usados:
        rid = u.get("recurso_id")
        if not rid:
            continue
        n += 1
        r = biblioteca.obtener(rid)
        if not r or not biblioteca.normalizar_licencia(r["licencia"]):
            malos.append(str(rid))
        elif r["licencia"] in ("cc-by", "cc-by-sa") and not r["credito"]:
            sin_credito += 1
    detalle = f"{n} recursos de terceros, todos con licencia comercial" if not malos else \
        f"Recursos sin licencia válida: {', '.join(malos)}"
    if sin_credito:
        detalle += f"; {sin_credito} CC BY sin autor registrado"
    return _item("Recursos con licencia", not malos and not sin_credito, detalle, 10, bloqueante=bool(malos))


def _titulo_ok(t: str) -> bool:
    if not t or len(t) > 100:
        return False
    mayus = re.findall(r"\b[A-ZÁÉÍÓÚÑ]{4,}\b", t)
    cebo = re.search(r"no vas a creer|incre[ií]ble|impactante|te sorprender[aá]|100% real", t, re.I)
    return len(mayus) <= 1 and not cebo


def _cerrar(items: List[Dict]) -> Dict:
    total = sum(i["peso"] for i in items)
    logrado = sum(i["peso"] for i in items if i["ok"])
    bloqueos = [i["nombre"] for i in items if i["bloqueante"] and not i["ok"]]
    return {"puntaje": int(round(logrado / total * 100)) if total else 0, "items": items, "bloqueos": bloqueos}
