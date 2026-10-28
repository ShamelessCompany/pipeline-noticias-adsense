"""
Agente Clipper: de un video o VOD largo saca los mejores momentos y los deja listos para revisión.

Cómo decide qué es un buen momento:
1. Energía del audio: picos sobre el nivel normal del stream (risas, gritos, reacciones).
2. Transcripción: marcas de risa, exclamaciones y palabras de reacción.
3. Un LLM lee los candidatos y puntúa si el tramo se entiende solo y tiene remate.
Los tres se combinan y se quedan los N mejores que no se pisan entre sí.
"""
import re
import shutil
import textwrap
import statistics
from pathlib import Path
from typing import Dict, List

from fabrica import db, llm, media, fuentes, subtitulos, metadatos, cumplimiento
from fabrica.agentes import ocupado, libre
from fabrica.ajustes import TRABAJOS_DIR, FORMATOS, obtener_nicho

REACCIONES = re.compile(
    r"jaj|jej|xd|\[risas\]|\[laughter\]|\[aplausos\]|no puede ser|qu[eé] (fue|pas[oó])|madre m[ií]a|"
    r"no manches|wtf|dios m[ií]o|en serio|no me lo creo|incre[ií]ble|ay no|qu[eé] asco|"
    r"oh my god|what the|no way|holy", re.I)

SISTEMA_MOMENTOS = """Eres editor de clips para YouTube. Te paso tramos candidatos de un stream o video
con su transcripción. Para cada uno decide si sirve como clip suelto.
Un buen clip: se entiende sin contexto previo, tiene un arranque claro y un remate (risa, giro, dato, anécdota).
Responde SOLO JSON: {"candidatos": [{"id": 0, "puntaje": 0-10, "categoria": "gracioso|anecdota|dato|polemica|epico|otro",
"titulo": "título corto y fiel", "gancho_pantalla": "máx 6 palabras para poner arriba",
"contexto": "1 frase que explica qué está pasando", "motivo": "por qué funciona o no"}]}"""


def _carpeta(trabajo_id: int) -> Path:
    d = TRABAJOS_DIR / f"{trabajo_id:05d}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _zscores(valores: List[float], ventana: int = 90) -> List[float]:
    """Cuánto sobresale cada segundo respecto al nivel de los ~90 s de alrededor."""
    out = []
    for i, v in enumerate(valores):
        tramo = valores[max(0, i - ventana // 2): i + ventana // 2]
        med = statistics.median(tramo)
        dev = statistics.pstdev(tramo) or 1.0
        out.append(max(0.0, (v - med) / dev))
    return out


def candidatos(energia: List[float], segmentos: List[Dict], dur_min: int, dur_max: int,
               n: int = 12) -> List[Dict]:
    total = len(energia)
    if total < dur_min:
        return [{"inicio": 0.0, "fin": float(total), "heuristico": 1.0}] if total > 5 else []
    z = _zscores(energia)
    puntos = list(z)
    for s in segmentos:
        hits = len(REACCIONES.findall(s["texto"])) + s["texto"].count("!") * 0.3
        if hits:
            for t in range(int(s["inicio"]), min(total, int(s["fin"]) + 1)):
                puntos[t] += hits * 0.8
    largo = int((dur_min + dur_max) / 2)
    ventanas = []
    for ini in range(0, max(1, total - dur_min), 3):
        fin = min(total, ini + largo)
        tramo = sorted(puntos[ini:fin], reverse=True)
        top = tramo[:max(1, len(tramo) // 4)]
        ventanas.append((sum(top) / len(top) + max(tramo) * 0.3, ini, fin))
    ventanas.sort(reverse=True)
    elegidos: List[Dict] = []
    for sc, ini, fin in ventanas:
        if all(fin <= e["inicio"] or ini >= e["fin"] for e in elegidos):
            # El pico debería caer en el último tercio: arrancar un poco antes para dar contexto
            pico = ini + max(range(fin - ini), key=lambda k: puntos[ini + k])
            ini2 = max(0, min(ini, pico - int(largo * 0.65)))
            fin2 = min(total, max(fin, pico + 6), ini2 + dur_max)
            ini2, fin2 = _ajustar_a_frases(ini2, fin2, segmentos, dur_min, dur_max)
            if all(fin2 <= e["inicio"] or ini2 >= e["fin"] for e in elegidos):
                elegidos.append({"inicio": float(ini2), "fin": float(fin2), "heuristico": round(sc, 2)})
        if len(elegidos) >= n:
            break
    return elegidos


def _ajustar_a_frases(ini: float, fin: float, segs: List[Dict], dmin: int, dmax: int):
    """Mueve los bordes al inicio/fin de frase más cercano para no cortar a media palabra."""
    if not segs:
        return ini, fin
    inicios = [s["inicio"] for s in segs if ini - 4 <= s["inicio"] <= ini + 3]
    finales = [s["fin"] for s in segs if fin - 3 <= s["fin"] <= fin + 4]
    a = min(inicios, key=lambda x: abs(x - ini)) if inicios else ini
    b = min(finales, key=lambda x: abs(x - fin)) if finales else fin
    if dmin <= b - a <= dmax + 4:
        return max(0, a - 0.2), b + 0.4
    return ini, fin


def _texto_en(segs: List[Dict], ini: float, fin: float) -> str:
    return " ".join(s["texto"] for s in segs if s["fin"] > ini and s["inicio"] < fin)


def puntuar_con_llm(cands: List[Dict], segs: List[Dict], titulo_fuente: str) -> List[Dict]:
    if not segs:
        return cands
    bloque = "\n\n".join(f"[id {i}] ({c['inicio']:.0f}s-{c['fin']:.0f}s)\n{_texto_en(segs, c['inicio'], c['fin'])[:1200]}"
                         for i, c in enumerate(cands))
    r = llm.generar_json(f"Video: {titulo_fuente}\n\n{bloque}", SISTEMA_MOMENTOS, temperatura=0.4)
    lista = (r or {}).get("candidatos", []) if isinstance(r, dict) else (r if isinstance(r, list) else [])
    for x in lista:
        try:
            c = cands[int(x["id"])]
        except Exception:
            continue
        c.update({k: x.get(k) for k in ("categoria", "titulo", "gancho_pantalla", "contexto", "motivo") if x.get(k)})
        c["llm"] = float(x.get("puntaje", 5))
    return cands


def analizar_fuente(t: Dict) -> None:
    """Etapa 1 (trabajo fuente_clip): bajar, transcribir, detectar y crear un trabajo por clip."""
    tid, url = t["id"], t["fuente_url"]
    nicho = obtener_nicho(t["nicho"])
    fmt = FORMATOS[t["formato"]]
    carpeta = _carpeta(tid)
    dmin, dmax = (fmt["seg_min"], fmt["seg_max"]) if t["formato"] == "short" else (60, 240)

    ocupado("clipper", f"Leyendo la fuente {url[:70]}", tid)
    es_local = Path(url).exists()
    info = {"titulo": Path(url).stem, "canal": "archivo local", "url": url} if es_local else fuentes.info_video(url)
    db.actualizar(tid, titulo=info["titulo"][:140], etapa="descargando", progreso=10)

    ocupado("clipper", f"Descargando «{info['titulo'][:60]}»", tid)
    video = carpeta / "fuente.mp4"
    if es_local:
        shutil.copy(url, video)
    else:
        video = fuentes.descargar(url, carpeta / "fuente")
    db.actualizar(tid, etapa="transcribiendo", progreso=35)

    ocupado("clipper", "Buscando subtítulos publicados o transcribiendo", tid)
    segs = None if es_local else fuentes.transcripcion_publicada(url)
    motor_trans = "subtitulos publicados"
    if not segs:
        try:
            audio = media.extraer_audio(str(video), str(carpeta / "fuente.wav"))
            r = subtitulos.transcribir(audio)
            segs, motor_trans = r["segmentos"], r["motor"]
        except Exception as e:
            db.registrar("Clipper", f"Sin transcripción ({e}); decido solo por energía del audio", tid, "aviso")
            segs, motor_trans = [], "ninguna"
    db.actualizar(tid, etapa="detectando momentos", progreso=60)

    ocupado("clipper", "Midiendo la energía del audio para encontrar reacciones", tid)
    energia = media.energia_audio(str(video)) if media.tiene_audio(str(video)) else [0.0] * int(media.duracion(str(video)))
    cands = candidatos(energia, segs, dmin, dmax, n=12)
    ocupado("clipper", f"{len(cands)} candidatos; los puntúa el LLM", tid)
    cands = puntuar_con_llm(cands, segs, info["titulo"])
    maxh = max([c["heuristico"] for c in cands] or [1]) or 1
    for c in cands:
        c["puntaje"] = round(0.5 * (c["heuristico"] / maxh * 10) + 0.5 * c.get("llm", c["heuristico"] / maxh * 10), 1)
    cands.sort(key=lambda c: c["puntaje"], reverse=True)

    n_clips = int(nicho.get("clips_por_video", 3))
    minimo = float(nicho.get("puntaje_min_clip", 4))
    elegidos = [c for c in cands if c["puntaje"] >= minimo][:n_clips] or cands[:1]
    for i, c in enumerate(elegidos):
        hijo = db.crear_trabajo(
            "clip", t["nicho"], t["formato"], fuente_url=url,
            titulo=c.get("titulo") or f"{info['titulo'][:60]} (momento {i + 1})", padre_id=tid,
            datos={"inicio": c["inicio"], "fin": c["fin"], "momento": c,
                   "fuente_info": info, "video_fuente": str(video),
                   "transcripcion": _texto_en(segs, c["inicio"], c["fin"]),
                   "segmentos": [s for s in segs if s["fin"] > c["inicio"] and s["inicio"] < c["fin"]],
                   "permiso_manual": t["datos"].get("permiso_manual", False)})
        db.registrar("Clipper", f"Momento {c['inicio']:.0f}s-{c['fin']:.0f}s puntaje {c['puntaje']} "
                                f"({c.get('categoria', 'sin categoría')}) → trabajo #{hijo}", tid)
    db.fusionar_datos(tid, fuente_info=info, candidatos=cands, motor_transcripcion=motor_trans,
                      energia_resumen=energia[::max(1, len(energia) // 300)])
    db.actualizar(tid, estado="analizado", etapa="clips creados", progreso=100)
    libre("clipper", f"«{info['titulo'][:50]}»: {len(elegidos)} clips en cola", tid)


def producir_clip(t: Dict) -> None:
    """Etapa 2 (trabajo clip): recortar, subtitular, narrar contexto, reencuadrar y empaquetar."""
    tid, d = t["id"], t["datos"]
    nicho = obtener_nicho(t["nicho"])
    fmt = FORMATOS[t["formato"]]
    carpeta = _carpeta(tid)
    info, momento = d.get("fuente_info", {}), d.get("momento", {})

    ocupado("clipper", f"Recortando {d['inicio']:.0f}s-{d['fin']:.0f}s", tid)
    if Path(d["video_fuente"]).exists():
        crudo = media.cortar(d["video_fuente"], d["inicio"], d["fin"], str(carpeta / "crudo.mp4"))
    else:
        # El VOD ya se borró en la limpieza: bajar solo este tramo
        tramo = fuentes.descargar(t["fuente_url"], carpeta / "tramo", inicio=d["inicio"], fin=d["fin"])
        crudo = media.cortar(str(tramo), 0, d["fin"] - d["inicio"], str(carpeta / "crudo.mp4"))
    libre("clipper")
    db.actualizar(tid, etapa="subtitulando", progreso=25)

    ocupado("locutor", "Transcribiendo el clip palabra por palabra", tid)
    if media.tiene_audio(crudo):
        texto_conocido = d.get("transcripcion", "")
        r = subtitulos.palabras_de_audio(crudo, texto_conocido)
        palabras = r["palabras"]
    else:
        palabras = []
    ass = subtitulos.escribir_ass(palabras, str(carpeta / "subs.ass"), fmt["ancho"], fmt["alto"],
                                  color=nicho.get("color_subtitulos", "amarillo")) if palabras else None
    libre("locutor")

    ocupado("empaquetador", "Decidiendo título, descripción y tags", tid)
    creditos = [f"Clip de {info.get('canal', 'creador original')}: {info.get('url', t['fuente_url'])}",
                "Fuente usada con permiso del creador." if cumplimiento.fuente_permitida(t["fuente_url"])["permite_clips"] else ""]
    contenido = " ".join(x for x in (momento.get("contexto", ""), d.get("transcripcion", "")) if x)
    meta = metadatos.generar(contenido or info.get("titulo", ""), nicho, t["formato"], [c for c in creditos if c],
                             _formulas(t["nicho"]), pista_titulo=momento.get("titulo") or t["titulo"])
    libre("empaquetador")
    db.actualizar(tid, etapa="narrando contexto", progreso=50)

    intro = None
    if nicho.get("clip_intro_narrada", True) and momento.get("contexto"):
        ocupado("locutor", "Grabando una intro corta con contexto propio", tid)
        v = media.sintetizar_voz(momento["contexto"], str(carpeta / "intro.mp3"), nicho.get("voz", "es-MX-JorgeNeural"))
        intro = None if v["simulada"] else v["ruta"]
        libre("locutor")

    ocupado("editor", "Reencuadrando a " + ("vertical 9:16" if t["formato"] == "short" else "16:9"), tid)
    gancho = momento.get("gancho_pantalla") or textwrap.shorten(meta["titulo"], 44, placeholder="…")
    final = media.reencuadrar(crudo, str(carpeta / "final.mp4"), fmt["ancho"], fmt["alto"], ass=ass,
                              titulo=gancho, modo=nicho.get("reencuadre", "desenfoque"),
                              intro_audio=intro if media.tiene_audio(crudo) else None)
    media.miniatura(final, str(carpeta / "mini.jpg"), 1.0)
    libre("editor", "Clip montado", tid)

    ocupado("revisor", "Comprobando normas de monetización", tid)
    datos_rev = {"duracion": media.duracion(final), "titulo_overlay": gancho, "subtitulos": bool(ass),
                 "intro_narrada": bool(intro)}
    rev = cumplimiento.revisar_clip(datos_rev, meta, t["fuente_url"], d.get("permiso_manual", False))
    libre("revisor", f"Puntaje {rev['puntaje']}/100" + (f", bloqueos: {', '.join(rev['bloqueos'])}" if rev["bloqueos"] else ""),
          tid, "ok" if not rev["bloqueos"] else "aviso")
    db.fusionar_datos(tid, video=str(final), miniatura=str(carpeta / "mini.jpg"), metadatos=meta,
                      revision=rev, gancho_pantalla=gancho, palabras_subs=len(palabras))
    db.actualizar(tid, titulo=meta["titulo"], estado="revision", etapa="listo para revisar", progreso=100,
                  puntaje=rev["puntaje"])


def _formulas(nicho_id: str) -> List[str]:
    from fabrica.ajustes import cargar_estilo
    return cargar_estilo(nicho_id).get("formulas_titulo", [])[:6]
