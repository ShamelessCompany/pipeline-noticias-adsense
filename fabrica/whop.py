"""
Campañas de clipping de Whop (Content Rewards): una marca o creador pone material y paga por
cada 1000 vistas de los clips que la gente publica en Shorts, TikTok o Reels.

Aquí vive todo lo propio de una campaña:
- Sus reglas (duración, formato, hashtags y menciones obligatorias, plataformas, CPM y topes).
- Lanzar el material de la campaña al Clipper con esas reglas.
- Ajustar título/descripción/captions a lo que pide la campaña y revisarlo antes de aprobar.
- Guardar los enlaces publicados, sus vistas y lo que se estima cobrar.

Muchas campañas rechazan clips automatizados o repetitivos, así que los clips de campaña
nunca se aprueban solos: siempre pasan por una persona en Revisión.
"""
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fabrica import db, llm

PLATAFORMAS = {
    "youtube": {"nombre": "YouTube Shorts", "dominios": ("youtube.com", "youtu.be")},
    "tiktok": {"nombre": "TikTok", "dominios": ("tiktok.com",)},
    "instagram": {"nombre": "Instagram Reels", "dominios": ("instagram.com",)},
    "x": {"nombre": "X", "dominios": ("x.com", "twitter.com")},
}
ESTADOS_CAMPANA = ["activa", "pausada", "cerrada"]
ESTADOS_ENVIO = ["publicado", "enviado", "aprobado", "rechazado", "pagado"]

CAMPANA_DEFECTO = {
    "url_whop": "", "marca": "", "nicho": "", "material": [], "plataformas": ["youtube", "tiktok", "instagram"],
    "formato": "short", "dur_min": 15, "dur_max": 60, "clips_por_video": 4, "hashtags": [], "menciones": [],
    "texto_obligatorio": "", "cpm": 0.0, "pago_max_clip": 0.0, "presupuesto": 0.0, "vistas_min": 0,
    "fecha_fin": "", "idioma": "es", "prohibe_automatizado": False, "intro_narrada": False,
    "subtitulos": True, "reencuadre": "desenfoque", "canal_youtube": "", "reglas_texto": "", "notas": "",
}

SISTEMA_REGLAS = """Te paso el texto de una campaña de clipping de Whop (Content Rewards).
Extrae las reglas. Si un dato no aparece, déjalo vacío o en 0; no inventes.
Responde SOLO JSON: {"nombre": "", "marca": "", "plataformas": ["youtube"|"tiktok"|"instagram"|"x"],
"formato": "short|largo", "dur_min": 0, "dur_max": 0, "hashtags": ["#..."], "menciones": ["@..."],
"texto_obligatorio": "frase que debe ir en la descripción o caption", "cpm": 0.0, "pago_max_clip": 0.0,
"presupuesto": 0.0, "vistas_min": 0, "fecha_fin": "AAAA-MM-DD", "idioma": "es|en|...",
"prohibe_automatizado": true|false, "material": ["enlaces al material fuente"], "notas": "otras reglas en 1-3 frases"}"""


# ---------------------------------------------------------------------------
# Campañas
# ---------------------------------------------------------------------------

def _fila(r) -> Dict[str, Any]:
    d = dict(r)
    try:
        d["datos"] = {**CAMPANA_DEFECTO, **json.loads(d.get("datos") or "{}")}
    except Exception:
        d["datos"] = dict(CAMPANA_DEFECTO)
    return d


def _lista(v) -> List[str]:
    if isinstance(v, str):
        v = re.split(r"[\s,]+", v)
    return [str(x).strip() for x in (v or []) if str(x).strip()]


def limpiar_datos(b: Dict) -> Dict[str, Any]:
    """Normaliza lo que llega del panel o del LLM a los tipos que espera el resto de la fábrica."""
    d = {k: b.get(k, v) for k, v in CAMPANA_DEFECTO.items()}
    d["material"] = [u for u in _lista(b.get("material")) if "://" in u or u.startswith(("/", "."))
                     or re.match(r"^[A-Za-z]:\\", u)]
    d["plataformas"] = list(dict.fromkeys(p for p in _lista(b.get("plataformas")) if p in PLATAFORMAS)) or ["youtube"]
    d["hashtags"] = list(dict.fromkeys("#" + h.lstrip("#") for h in _lista(b.get("hashtags"))))
    d["menciones"] = list(dict.fromkeys("@" + m.lstrip("@") for m in _lista(b.get("menciones"))))
    for k in ("dur_min", "dur_max", "clips_por_video", "vistas_min"):
        try:
            d[k] = int(float(b.get(k) or 0))
        except (TypeError, ValueError):
            d[k] = CAMPANA_DEFECTO[k]
    for k in ("cpm", "pago_max_clip", "presupuesto"):
        try:
            d[k] = round(float(str(b.get(k) or 0).replace("$", "").replace(",", ".")), 2)
        except (TypeError, ValueError):
            d[k] = 0.0
    d["dur_min"] = max(5, d["dur_min"] or CAMPANA_DEFECTO["dur_min"])
    d["dur_max"] = max(d["dur_min"] + 5, d["dur_max"] or CAMPANA_DEFECTO["dur_max"])
    d["clips_por_video"] = min(15, max(1, d["clips_por_video"] or 4))
    d["formato"] = "largo" if b.get("formato") == "largo" else "short"
    d["reencuadre"] = "recorte" if b.get("reencuadre") == "recorte" else "desenfoque"
    for k in ("prohibe_automatizado", "intro_narrada", "subtitulos"):
        d[k] = bool(b.get(k, CAMPANA_DEFECTO[k]))
    for k in ("url_whop", "marca", "nicho", "texto_obligatorio", "fecha_fin", "idioma", "canal_youtube", "reglas_texto", "notas"):
        d[k] = str(b.get(k) or "").strip()
    return d


def crear_campana(nombre: str, datos: Dict) -> int:
    with db._lock, db._conn() as c:
        cur = c.execute("INSERT INTO campanas (nombre, estado, datos, creado, actualizado) VALUES (?,?,?,?,?)",
                        (nombre.strip() or "Campaña sin nombre", "activa",
                         json.dumps(limpiar_datos(datos), ensure_ascii=False), db.ahora(), db.ahora()))
        cid = cur.lastrowid
    db.registrar("Whop", f"Campaña #{cid} «{nombre[:60]}» registrada")
    return cid


def actualizar_campana(cid: int, nombre: Optional[str] = None, estado: Optional[str] = None,
                       datos: Optional[Dict] = None) -> None:
    c0 = obtener_campana(cid)
    if not c0:
        return
    nuevo = limpiar_datos({**c0["datos"], **datos}) if datos is not None else c0["datos"]
    with db._lock, db._conn() as c:
        c.execute("UPDATE campanas SET nombre=?, estado=?, datos=?, actualizado=? WHERE id=?",
                  ((nombre or c0["nombre"]).strip(), estado if estado in ESTADOS_CAMPANA else c0["estado"],
                   json.dumps(nuevo, ensure_ascii=False), db.ahora(), cid))


def obtener_campana(cid: Optional[int]) -> Optional[Dict[str, Any]]:
    if not cid:
        return None
    with db._lock, db._conn() as c:
        r = c.execute("SELECT * FROM campanas WHERE id=?", (int(cid),)).fetchone()
        return _fila(r) if r else None


def listar_campanas() -> List[Dict[str, Any]]:
    with db._lock, db._conn() as c:
        rows = c.execute("SELECT * FROM campanas ORDER BY estado='activa' DESC, id DESC").fetchall()
    trabajos = db.listar(limite=5000)
    envs = listar_envios()
    return [{**_fila(r), "resumen": resumen(_fila(r), trabajos, envs)} for r in rows]


def borrar_campana(cid: int) -> None:
    """Archiva la campaña (no borra clips ni enlaces, que pueden seguir cobrándose)."""
    actualizar_campana(cid, estado="cerrada")


def de_trabajo(t: Dict) -> Optional[Dict[str, Any]]:
    return obtener_campana((t.get("datos") or {}).get("campana_id"))


def trabajos_de(cid: int, trabajos: Optional[List[Dict]] = None) -> List[Dict]:
    return [t for t in (trabajos if trabajos is not None else db.listar(limite=5000))
            if t["datos"].get("campana_id") == cid and t["estado"] != "descartado"]


def vencida(camp: Dict) -> bool:
    fin = camp["datos"].get("fecha_fin")
    return bool(fin) and fin < db.ahora()[:10]


# ---------------------------------------------------------------------------
# Leer las reglas pegadas desde la página de la campaña
# ---------------------------------------------------------------------------

def extraer_reglas(texto: str) -> Dict[str, Any]:
    """El LLM lee las reglas pegadas; si no hay LLM, se saca lo que se pueda con expresiones regulares."""
    base = reglas_por_patrones(texto)
    r = llm.generar_json(texto[:8000], SISTEMA_REGLAS, temperatura=0.1)
    if isinstance(r, dict):
        # Lo que el texto dice literalmente (hashtags, menciones, enlaces) se suma a lo que leyó el LLM
        for k in ("hashtags", "menciones", "material"):
            r[k] = list(dict.fromkeys(_lista(r.get(k)) + base.get(k, [])))
        base.update({k: v for k, v in r.items() if v not in (None, "", 0, [], 0.0)})
    base["reglas_texto"] = texto.strip()
    return {"nombre": base.pop("nombre", ""), **limpiar_datos(base)}


def reglas_por_patrones(texto: str) -> Dict[str, Any]:
    t = texto or ""
    low = t.lower()
    out: Dict[str, Any] = {
        "hashtags": list(dict.fromkeys(re.findall(r"#[\wáéíóúñ]+", t))),
        "menciones": list(dict.fromkeys(m.rstrip(".") for m in re.findall(r"(?<![\w.])@[\w.]{2,30}", t))),
        "material": list(dict.fromkeys(u.rstrip(").,") for u in re.findall(r"https?://\S+", t)
                                       if "whop.com" not in u)),
        "plataformas": [p for p, k in (("youtube", "youtube"), ("youtube", "shorts"), ("tiktok", "tiktok"),
                                       ("instagram", "instagram"), ("instagram", "reels"), ("x", "twitter"))
                        if k in low],
    }
    m = re.search(r"\$\s*([\d.,]+)\s*(?:/|per|por|x)\s*(?:1\s*k|1[.,]?000|mil|1000)", low)
    if m:
        out["cpm"] = m.group(1).replace(",", ".")
    m = re.search(r"(\d+)\s*(?:-|a|to|–)\s*(\d+)\s*(?:s\b|seg|sec)", low)
    if m:
        out["dur_min"], out["dur_max"] = m.group(1), m.group(2)
    else:
        m = re.search(r"(?:max(?:imo|imum)?|hasta|under|menos de)\s*(\d+)\s*(?:s\b|seg|sec)", low)
        if m:
            out["dur_max"] = m.group(1)
    m = re.search(r"(?:min(?:imo|imum)?\.?|al menos|at least)\s*([\d.,]+)\s*(k|mil)?\s*(?:views|vistas|visualizaciones)", low)
    if m:
        n = float(m.group(1).replace(",", "."))
        out["vistas_min"] = int(n * 1000) if m.group(2) else int(n)
    m = re.search(r"(?:max(?:imo|imum)?|tope|cap)\s*(?:de\s*)?(?:pago|payout|per clip|por clip)?\D{0,12}\$\s*([\d.,]+)", low)
    if m:
        out["pago_max_clip"] = m.group(1).replace(",", ".")
    out["prohibe_automatizado"] = bool(re.search(
        r"no (?:bots?|automat|ai[- ]generated|ia)|automated|automatizad|repetitiv|reupload|no spam", low))
    primera = next((l.strip() for l in t.splitlines() if l.strip()), "")
    out["nombre"] = re.sub(r"^(?:clipping\s+)?(?:campaign|campaña)\s*[:\-–]\s*", "", primera, flags=re.I)[:80]
    out["formato"] = "largo" if re.search(r"horizontal|16:9|landscape", low) and "vertical" not in low else "short"
    return out


# ---------------------------------------------------------------------------
# Producción: del material de la campaña al Clipper
# ---------------------------------------------------------------------------

def lanzar_material(cid: int, urls: Optional[List[str]] = None) -> List[int]:
    """Crea un trabajo fuente_clip por cada enlace de material (los ya lanzados se saltan)."""
    camp = obtener_campana(cid)
    if not camp:
        raise ValueError("La campaña no existe")
    if camp["estado"] != "activa":
        raise ValueError("La campaña no está activa")
    d = camp["datos"]
    nuevos = [u for u in (_lista(urls) if urls else d["material"])]
    if urls:
        actualizar_campana(cid, datos={"material": list(dict.fromkeys(d["material"] + nuevos))})
    lanzados = {t["fuente_url"] for t in trabajos_de(cid) if t["tipo"] == "fuente_clip"}
    from fabrica.ajustes import cargar_nichos
    nichos = cargar_nichos()
    nicho = d["nicho"] if any(n["id"] == d["nicho"] for n in nichos) else (nichos[0]["id"] if nichos else "general")
    ids = []
    for u in nuevos:
        if u in lanzados:
            continue
        # El material lo pone la propia campaña para que se recorte: ese es el permiso del creador
        tid = db.crear_trabajo("fuente_clip", nicho, d["formato"], fuente_url=u, titulo=f"[{camp['nombre'][:40]}] {u}",
                               datos={"campana_id": cid, "permiso_manual": True, "permiso_origen": "campaña Whop",
                                      "origen": "whop"})
        db.registrar("Whop", f"Material de «{camp['nombre'][:50]}» enviado al Clipper", tid)
        ids.append(tid)
    return ids


def ajustar_nicho(nicho: Dict, camp: Dict) -> Dict:
    """Las reglas de la campaña mandan sobre la configuración del nicho mientras se produce el clip."""
    d = camp["datos"]
    return {**nicho, "clips_por_video": d["clips_por_video"], "clip_intro_narrada": d["intro_narrada"],
            "reencuadre": d["reencuadre"], "puntaje_min_clip": nicho.get("puntaje_min_clip", 4),
            "tags_base": [h.lstrip("#").lower() for h in d["hashtags"]] + list(nicho.get("tags_base", []))}


def duraciones(camp: Dict) -> tuple:
    d = camp["datos"]
    # Margen de 2 s para que el ajuste a frases no se pase del máximo de la campaña
    return d["dur_min"], max(d["dur_min"] + 3, d["dur_max"] - 2)


def aplicar_metadatos(meta: Dict, camp: Dict) -> Dict:
    """Mete hashtags, menciones y texto obligatorio, y prepara un caption por plataforma."""
    d = camp["datos"]
    obligatorio = " ".join(x for x in [d["texto_obligatorio"], " ".join(d["menciones"])] if x).strip()
    desc = meta.get("descripcion", "")
    if obligatorio and obligatorio.lower() not in desc.lower():
        desc = obligatorio + "\n\n" + desc
    faltan = [h for h in d["hashtags"] if h.lower() not in desc.lower()]
    if faltan:
        desc = desc.rstrip() + "\n\n" + " ".join(faltan)
    meta = {**meta, "descripcion": desc.strip()}
    meta["captions"] = captions(meta, camp)
    return meta


def captions(meta: Dict, camp: Dict) -> Dict[str, str]:
    d = camp["datos"]
    titulo = meta.get("titulo", "")
    tags_extra = ["#" + t.replace(" ", "") for t in meta.get("tags", [])[:4]]
    etiquetas = list(dict.fromkeys(d["hashtags"] + tags_extra))
    cabeza = " ".join(x for x in [titulo, d["texto_obligatorio"], " ".join(d["menciones"])] if x)
    out = {}
    for p in d["plataformas"]:
        if p == "youtube":
            out[p] = meta.get("descripcion", "")
        elif p == "x":
            out[p] = (cabeza + " " + " ".join(d["hashtags"]))[:280]
        else:
            # TikTok y Reels: caption corto y hashtags al final (Instagram admite hasta 30)
            out[p] = (cabeza + "\n\n" + " ".join(etiquetas[:30]))[:2200]
    return out


def revisar(rev: Dict, camp: Dict, meta: Dict, t: Dict, duracion: float, ancho: int, alto: int) -> Dict:
    """Añade a la revisión del clip las reglas de la campaña y vuelve a puntuar."""
    from fabrica import cumplimiento
    d = camp["datos"]
    desc = meta.get("descripcion", "").lower()
    faltan_h = [h for h in d["hashtags"] if h.lower() not in desc]
    faltan_m = [m for m in d["menciones"] if m.lower() not in desc]
    vertical = alto > ancho
    otros = [o for o in trabajos_de(camp["id"]) if o["id"] != t["id"] and o["tipo"] == "clip"
             and o["fuente_url"] == t["fuente_url"]]
    pisa = [o["id"] for o in otros if _solape(t["datos"], o["datos"]) > 0.5]
    # La duración la manda la campaña, y si la campaña no quiere intro narrada no se penaliza no tenerla
    items = [i for i in rev["items"] if not i["nombre"].startswith("Duración")
             and not (i["nombre"] == "Contexto narrado" and not d["intro_narrada"])]
    items += [
        cumplimiento._item("Duración de la campaña", d["dur_min"] <= duracion <= d["dur_max"],
                           f"{duracion:.0f} s (la campaña pide {d['dur_min']}-{d['dur_max']} s)", 15, bloqueante=True),
        cumplimiento._item("Formato de la campaña", vertical == (d["formato"] == "short"),
                           "Vertical 9:16" if vertical else "Horizontal 16:9", 10, bloqueante=True),
        cumplimiento._item("Hashtags obligatorios", not faltan_h,
                           "Todos en la descripción" if not faltan_h else "Faltan " + " ".join(faltan_h), 10),
        cumplimiento._item("Menciones obligatorias", not faltan_m,
                           "Todas en la descripción" if not faltan_m else "Faltan " + " ".join(faltan_m), 10),
        cumplimiento._item("Campaña activa", camp["estado"] == "activa" and not vencida(camp),
                           f"Termina {d['fecha_fin']}" if d["fecha_fin"] else camp["estado"], 10, bloqueante=True),
        cumplimiento._item("No repite otro clip de la campaña", not pisa,
                           "Tramo distinto a los demás clips" if not pisa else
                           f"Comparte más de la mitad del tramo con #{', #'.join(map(str, pisa))}", 15, bloqueante=True),
    ]
    if d["prohibe_automatizado"]:
        items.append(cumplimiento._item(
            "Revisión humana (la campaña no admite clips automatizados)", False,
            "Míralo entero y edita título y caption a mano antes de aprobar", 5))
    return cumplimiento._cerrar(items)


def _solape(a: Dict, b: Dict) -> float:
    ini, fin = max(a.get("inicio", 0), b.get("inicio", 0)), min(a.get("fin", 0), b.get("fin", 0))
    largo = min(a.get("fin", 0) - a.get("inicio", 0), b.get("fin", 0) - b.get("inicio", 0)) or 1
    return max(0.0, fin - ini) / largo


# ---------------------------------------------------------------------------
# Enlaces publicados, vistas y pagos
# ---------------------------------------------------------------------------

def plataforma_de(url: str) -> str:
    u = url.lower()
    for k, p in PLATAFORMAS.items():
        if any(dom in u for dom in p["dominios"]):
            return k
    return ""


def registrar_envio(cid: int, url: str, trabajo_id: Optional[int] = None, plataforma: str = "") -> int:
    url = url.strip()
    if not re.match(r"^https?://", url):
        raise ValueError("Pega el enlace completo del video publicado (https://...)")
    plataforma = plataforma if plataforma in PLATAFORMAS else plataforma_de(url)
    if not plataforma:
        raise ValueError("No reconozco la plataforma de ese enlace")
    with db._lock, db._conn() as c:
        if c.execute("SELECT 1 FROM envios WHERE url=?", (url,)).fetchone():
            raise ValueError("Ese enlace ya está registrado")
        cur = c.execute("INSERT INTO envios (campana_id, trabajo_id, plataforma, url, creado, actualizado) "
                        "VALUES (?,?,?,?,?,?)", (cid, trabajo_id, plataforma, url, db.ahora(), db.ahora()))
        eid = cur.lastrowid
    if trabajo_id:
        t = db.obtener(trabajo_id)
        if t and t["estado"] != "publicado":
            db.actualizar(trabajo_id, estado="publicado", etapa=f"publicado en {PLATAFORMAS[plataforma]['nombre']}")
    db.registrar("Whop", f"Enlace de {PLATAFORMAS[plataforma]['nombre']} registrado para la campaña #{cid}", trabajo_id)
    return eid


def listar_envios(cid: Optional[int] = None) -> List[Dict[str, Any]]:
    with db._lock, db._conn() as c:
        if cid:
            rows = c.execute("SELECT * FROM envios WHERE campana_id=? ORDER BY id DESC", (cid,))
        else:
            rows = c.execute("SELECT * FROM envios ORDER BY id DESC")
        return [dict(r) for r in rows.fetchall()]


def obtener_envio(eid: int) -> Optional[Dict[str, Any]]:
    with db._lock, db._conn() as c:
        r = c.execute("SELECT * FROM envios WHERE id=?", (eid,)).fetchone()
        return dict(r) if r else None


def actualizar_envio(eid: int, **campos) -> None:
    permitidos = {k: v for k, v in campos.items() if k in ("estado", "vistas", "pago", "notas", "vistas_actualizadas")}
    if "estado" in permitidos and permitidos["estado"] not in ESTADOS_ENVIO:
        permitidos.pop("estado")
    if not permitidos:
        return
    permitidos["actualizado"] = db.ahora()
    sets = ", ".join(f"{k}=?" for k in permitidos)
    with db._lock, db._conn() as c:
        c.execute(f"UPDATE envios SET {sets} WHERE id=?", (*permitidos.values(), eid))


def borrar_envio(eid: int) -> None:
    with db._lock, db._conn() as c:
        c.execute("DELETE FROM envios WHERE id=?", (eid,))


def leer_vistas(eid: int) -> int:
    """Lee las vistas públicas del enlace con yt-dlp (YouTube y TikTok casi siempre; Instagram a veces)."""
    from fabrica import fuentes
    e = obtener_envio(eid)
    if not e:
        raise ValueError("Ese enlace no existe")
    vistas = int(fuentes.info_video(e["url"]).get("vistas") or 0)
    if vistas:
        actualizar_envio(eid, vistas=vistas, vistas_actualizadas=db.ahora())
    return vistas


def actualizar_todas_las_vistas() -> int:
    n = 0
    for e in listar_envios():
        if e["estado"] in ("rechazado", "pagado"):
            continue
        try:
            leer_vistas(e["id"])
            n += 1
        except Exception as ex:
            db.registrar("Whop", f"No pude leer las vistas de {e['url'][:60]}: {str(ex)[:120]}", e["trabajo_id"], "aviso")
    return n


def ganancia(vistas: int, camp: Dict) -> float:
    d = camp["datos"]
    if not d["cpm"] or vistas < d["vistas_min"]:
        return 0.0
    g = vistas / 1000 * d["cpm"]
    return round(min(g, d["pago_max_clip"]) if d["pago_max_clip"] else g, 2)


def pendiente_de_subir(t: Dict, camp: Dict, envs: List[Dict]) -> bool:
    """Aprobado y todavía le falta el enlace de alguna de las plataformas de la campaña."""
    if t["estado"] in ("aprobado", "programado"):
        return True
    hechas = {e["plataforma"] for e in envs if e["trabajo_id"] == t["id"]}
    return t["estado"] == "publicado" and not set(camp["datos"]["plataformas"]) <= hechas


def resumen(camp: Dict, trabajos: Optional[List[Dict]] = None, envs: Optional[List[Dict]] = None) -> Dict[str, Any]:
    ts = trabajos_de(camp["id"], trabajos)
    clips = [t for t in ts if t["tipo"] == "clip"]
    es = [e for e in (envs if envs is not None else listar_envios(camp["id"])) if e["campana_id"] == camp["id"]]
    validos = [e for e in es if e["estado"] != "rechazado"]
    return {
        "material": len([t for t in ts if t["tipo"] == "fuente_clip"]),
        "produciendo": len([t for t in ts if t["estado"] in ("en_cola", "procesando")]),
        "revision": len([c for c in clips if c["estado"] == "revision"]),
        "listos": len([c for c in clips if pendiente_de_subir(c, camp, es)]),
        "publicados": len([c for c in clips if c["estado"] == "publicado"]),
        "errores": len([t for t in ts if t["estado"] == "error"]),
        "enlaces": len(es),
        "vistas": sum(e["vistas"] for e in validos),
        "estimado": round(sum(ganancia(e["vistas"], camp) for e in validos), 2),
        "cobrado": round(sum(e["pago"] for e in es if e["estado"] == "pagado"), 2),
        "vencida": vencida(camp),
    }
