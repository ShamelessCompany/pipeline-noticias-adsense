"""
Director de montaje: decide qué aparece en pantalla y cuándo, a partir de lo que dice el locutor.

1. Alinea cada escena del guion con los tiempos reales de las palabras.
2. Parte cada escena en planos según el ritmo de la receta del nicho (cortes por minuto).
3. Planifica insertos sincronizados: cifras cuando se dice un número, la foto de la persona o el lugar
   cuando se nombra, palabras clave, rótulos de capítulo, citas, zooms de golpe y efectos de sonido.
4. Resuelve cada inserto con la biblioteca, los bancos libres o los gráficos generados, y lo renderiza.

La receta sale del Analista de edición (data/estilos/<nicho>.json → "edicion") o de RECETAS por formato.
"""
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional

from fabrica import llm, broll, graficos, biblioteca, investigacion

RECETAS = {
    "short": {"plano_medio_s": 2.8, "insertos_por_min": 14, "cifras": True, "imagenes": True,
              "palabras_clave": True, "rotulos": False, "citas": True, "zoom_punch": True,
              "sfx_cortes": 0.5, "sfx_insertos": True, "origen": "por defecto"},
    "largo": {"plano_medio_s": 5.5, "insertos_por_min": 4, "cifras": True, "imagenes": True,
              "palabras_clave": False, "rotulos": True, "citas": True, "zoom_punch": True,
              "sfx_cortes": 0.25, "sfx_insertos": True, "origen": "por defecto"},
}

DUR_INSERTO = {"cifra": 1.8, "imagen": 2.6, "palabra": 1.3, "rotulo": 3.0, "cita": 3.2, "lugar": 2.4}
SFX_INSERTO = {"cifra": "impacto", "imagen": "pop", "palabra": "pop", "rotulo": "whoosh", "cita": "ding", "lugar": "pop"}

SISTEMA_DIRECTOR = """Eres editor de video de YouTube. Te paso las escenas de un guion ya locutado.
Propón INSERTOS que refuercen lo que se dice en ese instante, como hacen los canales grandes:
- "cifra": cuando se dice un número importante (texto = el número tal como se muestra, etiqueta = qué mide).
- "imagen": cuando se nombra una persona, objeto, obra o lugar concreto (busqueda = 2-4 palabras en INGLÉS).
- "lugar": cuando se nombra un sitio y conviene situarlo (texto = nombre, etiqueta = país o detalle).
- "palabra": una palabra o frase corta que conviene remarcar (máx 3 palabras).
- "rotulo": inicio de un bloque nuevo (texto = título corto, etiqueta = subtítulo).
- "cita": una frase textual de alguien (texto = la cita, etiqueta = autor).
ancla = la palabra EXACTA del texto de la escena donde debe aparecer.
No inventes datos que no estén en el texto. Como máximo un inserto cada 5 segundos.
Responde SOLO JSON: {"insertos": [{"escena": 0, "tipo": "...", "ancla": "...", "texto": "...", "etiqueta": "...", "busqueda": "..."}]}"""

VACIAS_NOMBRE = {"El", "La", "Los", "Las", "Un", "Una", "Y", "Pero", "Hay", "Esto", "Eso", "Este", "Esta", "Ahora",
                 "Primero", "Otro", "Otra", "Piénsalo", "Cuéntame", "Tú", "Yo", "Si", "No", "Sí", "Por", "Para",
                 "Con", "Cuando", "Donde", "Aquí", "Así", "Más", "Qué", "Quién", "Cómo", "Hoy", "En", "De", "Al", "Lo"}


def _norm(s: str) -> str:
    s = "".join(ch for ch in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9ñ%]", "", s)


def receta(nicho_id: str, formato: str) -> Dict:
    from fabrica.ajustes import cargar_estilo
    r = dict(RECETAS.get(formato, RECETAS["short"]))
    aprendida = (cargar_estilo(nicho_id) or {}).get("edicion", {}).get(formato)
    if aprendida:
        r.update({k: v for k, v in aprendida.items() if k in r or k in ("cortes_por_min", "muestras")})
        r["origen"] = "aprendida de los canales de referencia"
    return r


# ---------------------------------------------------------------------------
# Tiempos
# ---------------------------------------------------------------------------

def alinear_escenas(escenas: List[Dict], palabras: List[Dict], total: float) -> List[Dict]:
    """Devuelve cada escena con inicio, fin y el tramo de palabras (con tiempos) que le toca."""
    conteos = [max(1, len(e["texto"].split())) for e in escenas]
    suma, n = sum(conteos), len(palabras)
    out, acum = [], 0
    for i, (e, c) in enumerate(zip(escenas, conteos)):
        a = round(acum * n / suma)
        acum += c
        b = n if i == len(escenas) - 1 else round(acum * n / suma)
        tramo = palabras[a:b]
        ini = tramo[0]["inicio"] if tramo else (out[-1]["fin"] if out else 0.0)
        out.append({**e, "indice": i, "inicio": ini, "palabras_t": tramo})
    for i, e in enumerate(out):
        e["fin"] = out[i + 1]["inicio"] if i + 1 < len(out) else total
        if i == 0:
            e["inicio"] = 0.0
    return out


def _momento(escena: Dict, ancla: str) -> float:
    """Segundo en que se dice 'ancla' dentro de la escena (o una estimación por posición)."""
    objetivo = [_norm(w) for w in ancla.split() if _norm(w)]
    pal = escena["palabras_t"]
    if objetivo:
        for k, p in enumerate(pal):
            if _norm(p["palabra"]) == objetivo[0] or (len(objetivo[0]) > 4 and _norm(p["palabra"]).startswith(objetivo[0][:5])):
                return max(escena["inicio"], p["inicio"] - 0.1)
        texto = [_norm(w) for w in escena["texto"].split()]
        if objetivo[0] in texto:
            k = texto.index(objetivo[0]) / max(1, len(texto))
            return escena["inicio"] + k * (escena["fin"] - escena["inicio"])
    return escena["inicio"] + 0.2


# ---------------------------------------------------------------------------
# Plan de insertos
# ---------------------------------------------------------------------------

def _insertos_heuristicos(escenas: List[Dict], rec: Dict, formato: str) -> List[Dict]:
    out = []
    for e in escenas:
        palabras = e["texto"].split()
        # Cifras: números con dígitos (y su unidad o lo que miden)
        if rec["cifras"]:
            for k, w in enumerate(palabras):
                limpio = w.strip(".,;:¿?¡!()\"«»")
                if re.search(r"\d", limpio) and not re.fullmatch(r"(1[0-9]|20)\d\d", limpio) or \
                        re.fullmatch(r"\d+%", limpio):
                    numero = limpio
                    sig = [x.strip(".,;:") for x in palabras[k + 1:k + 5]]
                    if sig and sig[0].lower() in ("%", "por", "millones", "mil", "km", "kilómetros", "metros", "años", "veces"):
                        numero += " " + ("%" if sig[0].lower() == "por" else sig[0])
                        sig = sig[2:] if sig[0].lower() == "por" else sig[1:]
                    out.append({"escena": e["indice"], "tipo": "cifra", "ancla": limpio, "texto": numero,
                                "etiqueta": " ".join(sig[:3]), "fuente": "heurística"})
                    break
                elif re.fullmatch(r"(1[0-9]|20)\d\d", limpio) and formato == "largo":
                    out.append({"escena": e["indice"], "tipo": "rotulo", "ancla": limpio, "texto": limpio,
                                "etiqueta": e.get("texto_pantalla", ""), "fuente": "heurística"})
                    break
        # Nombres propios: palabras con mayúscula que no abren frase (se juntan las seguidas)
        if rec["imagenes"]:
            nombres, actual, desde = [], [], 0
            for k, w in enumerate(palabras):
                limpio = w.strip(".,;:¿?¡!()\"«»")
                abre = k == 0 or palabras[k - 1][-1:] in ".!?¿¡:"
                if abre and k + 1 < len(palabras) and palabras[k + 1][:1].isupper() and w[-1:] not in ".,;:!?":
                    abre = False  # «Gustave Eiffel …» al principio de la frase sigue siendo un nombre
                if limpio[:1].isupper() and len(limpio) >= 3 and not abre and limpio not in VACIAS_NOMBRE:
                    if not actual:
                        desde = k
                    actual.append(limpio)
                    if w[-1:] in ".,;:!?":
                        nombres.append((desde, actual))
                        actual = []
                else:
                    if actual:
                        nombres.append((desde, actual))
                    actual = []
            if actual:
                nombres.append((desde, actual))
            for k, nm in nombres[:1]:
                previa = palabras[k - 1].lower() if k else ""
                tipo = "lugar" if previa in ("en", "desde", "hacia", "a") and len(nm) <= 3 else "imagen"
                out.append({"escena": e["indice"], "tipo": tipo, "ancla": nm[0], "texto": " ".join(nm),
                            "etiqueta": "", "busqueda": " ".join(nm), "fuente": "heurística"})
        # Citas entre comillas
        if rec["citas"]:
            m = re.search(r"[«\"“]([^»\"”]{12,140})[»\"”]", e["texto"])
            if m:
                out.append({"escena": e["indice"], "tipo": "cita", "ancla": m.group(1).split()[0],
                            "texto": m.group(1), "etiqueta": "", "fuente": "heurística"})
        if rec["rotulos"] and e["indice"] > 0 and e["indice"] % 4 == 0 and e.get("texto_pantalla"):
            out.append({"escena": e["indice"], "tipo": "rotulo", "ancla": palabras[0] if palabras else "",
                        "texto": e["texto_pantalla"], "etiqueta": "", "fuente": "heurística"})
        if rec["palabras_clave"] and e["indice"] % 2 == 1:
            clave = investigacion.palabras_clave(e["texto"], 1)
            if clave:
                original = next((w.strip(".,;:¿?¡!") for w in palabras if _norm(w) == _norm(clave[0])), clave[0])
                out.append({"escena": e["indice"], "tipo": "palabra", "ancla": original, "texto": original,
                            "etiqueta": "", "fuente": "heurística"})
    return out


def _insertos_llm(escenas: List[Dict], rec: Dict) -> List[Dict]:
    texto = "\n".join(f"[{e['indice']}] ({e['fin'] - e['inicio']:.1f} s) {e['texto']}" for e in escenas)
    permitidos = [t for t, k in (("cifra", "cifras"), ("imagen", "imagenes"), ("lugar", "imagenes"),
                                 ("palabra", "palabras_clave"), ("rotulo", "rotulos"), ("cita", "citas")) if rec[k]]
    r = llm.generar_json(f"TIPOS PERMITIDOS: {', '.join(permitidos)}\nESCENAS:\n{texto}", SISTEMA_DIRECTOR, temperatura=0.4)
    out = []
    for it in (r or {}).get("insertos", []) if isinstance(r, dict) else []:
        try:
            i = int(it.get("escena", -1))
        except (TypeError, ValueError):
            continue
        if 0 <= i < len(escenas) and it.get("tipo") in permitidos and (it.get("texto") or it.get("busqueda")):
            out.append({**it, "escena": i, "fuente": "modelo"})
    return out


def planificar(escenas: List[Dict], palabras: List[Dict], total: float, formato: str, nicho_id: str) -> Dict:
    rec = receta(nicho_id, formato)
    al = alinear_escenas(escenas, palabras, total)
    propuestos = _insertos_llm(al, rec)
    motor = "modelo" if propuestos else "heurística"
    # Lo que el modelo no cubrió (p. ej. números) lo completa la heurística
    cubiertas = {(p["escena"], p["tipo"]) for p in propuestos}
    propuestos += [h for h in _insertos_heuristicos(al, rec, formato) if (h["escena"], h["tipo"]) not in cubiertas]

    for p in propuestos:
        p["inicio"] = round(_momento(al[p["escena"]], str(p.get("ancla") or p.get("texto") or "")), 2)
        p["dur"] = DUR_INSERTO.get(p["tipo"], 2.0)
    # Orden por turnos entre tipos para que no se lo coman todo las cifras
    prioridad = ["cifra", "imagen", "cita", "lugar", "rotulo", "palabra"]
    grupos = {t: [p for p in propuestos if p["tipo"] == t] for t in prioridad}
    propuestos = [g.pop(0) for _ in range(len(propuestos)) for g in grupos.values() if g]
    maximo = max(1, int(rec["insertos_por_min"] * total / 60))
    elegidos: List[Dict] = []
    for p in propuestos:
        if len(elegidos) >= maximo:
            break
        if p["inicio"] + 0.6 > total:
            continue
        if any(abs(p["inicio"] - q["inicio"]) < max(q["dur"], p["dur"]) * 0.9 for q in elegidos):
            continue
        p["dur"] = min(p["dur"], total - p["inicio"] - 0.1)
        elegidos.append(p)
    elegidos.sort(key=lambda p: p["inicio"])
    return {"receta": rec, "escenas": al, "insertos": elegidos, "motor": motor}


# ---------------------------------------------------------------------------
# Resolver: planos de fondo, capas, zooms y efectos
# ---------------------------------------------------------------------------

def _consultas_plano(e: Dict, k: int) -> str:
    if k == 0:
        return e.get("busqueda_visual") or e.get("texto_pantalla") or e["texto"][:40]
    claves = investigacion.palabras_clave(e["texto"], 3)
    return " ".join(claves[k - 1:k + 1]) or e.get("busqueda_visual") or e["texto"][:40]


def resolver(plan: Dict, carpeta: Path, ancho: int, alto: int, nicho: Dict, formato: str) -> Dict:
    rec = plan["receta"]
    vertical = alto > ancho
    color = nicho.get("color_subtitulos", "amarillo")
    usados: set = set()
    visuales: List[Dict] = []
    # Planos de fondo: cada escena se parte en tantos planos como pida el ritmo
    for e in plan["escenas"]:
        dur = max(0.8, e["fin"] - e["inicio"])
        n = max(1, min(4, round(dur / rec["plano_medio_s"])))
        for k in range(n):
            q = _consultas_plano(e, k)
            v = broll.buscar_visual(q, vertical, carpeta / f"tarjeta_{e['indice']:02d}_{k}.jpg",
                                    e.get("texto_pantalla") or e["texto"][:50], ancho, alto,
                                    len(visuales), nicho=nicho.get("id", ""), excluir=usados)
            if v.get("recurso_id"):
                usados.add(v["recurso_id"])
            v["dur"] = dur / n
            v["escena"] = e["indice"]
            visuales.append(v)

    capas, sfx, zooms, insertos = [], [], [], []
    for j, p in enumerate(plan["insertos"]):
        dst = str(carpeta / f"capa_{j:02d}.png")
        capa, credito, rid = None, "", None
        try:
            if p["tipo"] == "cifra":
                capa = graficos.cifra(p["texto"], p.get("etiqueta", ""), dst, ancho, alto, color)
            elif p["tipo"] == "palabra":
                capa = graficos.palabra(p["texto"], dst, ancho, alto, color)
            elif p["tipo"] == "rotulo":
                capa = graficos.rotulo(p["texto"], p.get("etiqueta", ""), dst, ancho, alto, color)
            elif p["tipo"] == "cita":
                capa = graficos.cita(p["texto"], p.get("etiqueta", ""), dst, ancho, alto, color)
            elif p["tipo"] in ("imagen", "lugar"):
                r = broll.buscar_recurso(p.get("busqueda") or p["texto"], vertical, "imagen",
                                         nicho=nicho.get("id", ""), excluir=usados)
                if r and r["tipo"] == "imagen":
                    capa = graficos.marco(r["ruta"], dst, ancho, alto, posicion="derecha")
                    credito, rid = r.get("credito", ""), r.get("recurso_id")
                    if rid:
                        usados.add(rid)
                elif p["tipo"] == "lugar" or p.get("texto"):
                    capa = graficos.lugar(p["texto"], p.get("etiqueta", ""), dst, ancho, alto, color) \
                        if p["tipo"] == "lugar" else graficos.palabra(p["texto"], dst, ancho, alto, color)
        except Exception as ex:
            print(f"[Montaje] Inserto {p['tipo']} descartado: {ex}")
            capa = None
        if not capa:
            continue
        capas.append({**capa, "inicio": p["inicio"], "dur": p["dur"]})
        if rec["sfx_insertos"]:
            s = graficos.sfx(SFX_INSERTO.get(p["tipo"], "pop") if capa["anim"] != "deslizar" else "whoosh")
            if s:
                sfx.append({"ruta": s, "inicio": p["inicio"], "volumen": 0.55})
        if rec["zoom_punch"] and p["tipo"] in ("cifra", "cita"):
            zooms.append({"inicio": p["inicio"], "dur": 0.45, "escala": 1.08})
        insertos.append({"tipo": p["tipo"], "inicio": p["inicio"], "dur": round(p["dur"], 2), "texto": p.get("texto", ""),
                         "credito": credito, "recurso_id": rid, "fuente": p.get("fuente", "")})

    # Efecto en una parte de los cortes (de forma regular, no aleatoria, para que sea reproducible)
    if rec["sfx_cortes"] > 0:
        cada = max(1, round(1 / rec["sfx_cortes"]))
        t, whoosh = 0.0, graficos.sfx("whoosh")
        for k, v in enumerate(visuales[:-1]):
            t += v["dur"]
            if whoosh and k % cada == 0 and not any(abs(t - s["inicio"]) < 0.6 for s in sfx):
                sfx.append({"ruta": whoosh, "inicio": max(0.0, t - 0.25), "volumen": 0.35})

    for rid in {v.get("recurso_id") for v in visuales} | {i["recurso_id"] for i in insertos}:
        if rid:
            biblioteca.marcar_uso(rid)
    creditos = sorted({v["credito"] for v in visuales if v.get("credito")} |
                      {i["credito"] for i in insertos if i["credito"]})
    return {"visuales": visuales, "capas": capas, "sfx": sfx, "zooms": zooms, "insertos": insertos,
            "creditos": creditos}


def dirigir(escenas: List[Dict], palabras: List[Dict], audio: str, ass: Optional[str], dst: str,
            carpeta: Path, ancho: int, alto: int, nicho: Dict, formato: str, musica: Optional[str] = None) -> Dict:
    """Planifica, resuelve y monta. Devuelve el resumen para guardar en el trabajo."""
    from fabrica import media
    total = media.duracion(audio) + 0.5
    plan = planificar(escenas, palabras, total, formato, nicho.get("id", ""))
    res = resolver(plan, carpeta, ancho, alto, nicho, formato)
    media.montar(res["visuales"], audio, ass, dst, ancho, alto, musica=musica, trabajo_dir=carpeta,
                 capas=res["capas"], sfx=res["sfx"], zooms=res["zooms"])
    return {**res, "receta": plan["receta"], "motor": plan["motor"],
            "cortes": len(res["visuales"]), "cortes_por_min": round(len(res["visuales"]) * 60 / total, 1)}
