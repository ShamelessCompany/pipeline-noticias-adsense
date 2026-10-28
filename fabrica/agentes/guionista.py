"""
Agente Guionista + Locutor + Editor para videos originales.

Entrada: un tema suelto o un video de referencia. Del video solo se toma el tema y los datos;
el guion se escribe de cero con otro ángulo, se investiga en fuentes libres, se pasa por el
filtro anti-IA y se monta con B-roll de bancos libres o tarjetas propias.
"""
import re
from pathlib import Path
from typing import Dict, List

from fabrica import db, llm, media, fuentes, subtitulos, metadatos, cumplimiento, estilo, investigacion, broll, montaje
from fabrica.agentes import ocupado, libre
from fabrica.ajustes import TRABAJOS_DIR, FORMATOS, obtener_nicho, cargar_estilo

SISTEMA_GUION = """Eres guionista de YouTube en español. Escribes guiones ORIGINALES para locución.
Te paso un tema, datos de investigación y, a veces, la transcripción de otro video sobre lo mismo.
Ese video es solo inspiración: NO copies frases, NO sigas su orden, busca un ángulo propio
(una pregunta que no responde, un dato que no menciona, una comparación nueva).
Escribe como habla una persona: frases de largo variado, nada de rayas largas (—), nada de
"en el mundo actual", "cabe destacar", "sumérgete", "fascinante", "crucial", "en conclusión".
No inventes cifras: usa solo las de la investigación o habla sin cifras.
Responde SOLO JSON:
{"titulo_trabajo": "...", "angulo": "qué aporta este video que no aporta la referencia",
 "escenas": [{"texto": "lo que dice el locutor en esta escena",
              "busqueda_visual": "2-4 palabras en INGLÉS para buscar B-roll",
              "texto_pantalla": "máx 6 palabras que aparecen en pantalla"}]}"""


def _carpeta(tid: int) -> Path:
    d = TRABAJOS_DIR / f"{tid:05d}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _referencia(t: Dict, carpeta: Path) -> Dict:
    url = t["fuente_url"]
    if not url:
        return {"titulo": t["titulo"] or t["datos"].get("tema", ""), "texto": "", "url": ""}
    if Path(url).exists():
        r = subtitulos.palabras_de_audio(media.extraer_audio(url, str(carpeta / "ref.wav")))
        return {"titulo": Path(url).stem, "texto": " ".join(s["texto"] for s in r["segmentos"]), "url": url, "canal": "local"}
    info = fuentes.info_video(url)
    segs = fuentes.transcripcion_publicada(url)
    if not segs:
        audio = fuentes.descargar(url, carpeta / "ref", max_alto=360)
        segs = subtitulos.transcribir(media.extraer_audio(str(audio), str(carpeta / "ref.wav")))["segmentos"]
    return {"titulo": info["titulo"], "texto": fuentes.texto_plano(segs), "url": url, "canal": info["canal"]}


def guion_respaldo(tema: str, dossier: Dict, palabras: int) -> Dict:
    """Sin LLM: arma un guion simple con datos de la investigación, en escenas cortas."""
    frases = []
    for f in dossier.get("fuentes", []):
        frases += [s.strip() for s in re.split(r"(?<=[.!?])\s+", f["texto"]) if 40 < len(s.strip()) < 220]
    frases = frases[:max(4, palabras // 22)]
    escenas = [{"texto": f"Hay algo de {tema} que casi nadie cuenta bien.", "busqueda_visual": tema,
                "texto_pantalla": tema[:40]}]
    conectores = ["Primero, lo básico.", "Ahora, el detalle raro.", "Y aquí cambia todo.", "Otro dato.", "Piénsalo así."]
    for i, f in enumerate(frases):
        escenas.append({"texto": f"{conectores[i % len(conectores)]} {f}",
                        "busqueda_visual": " ".join(investigacion.palabras_clave(f, 2)) or tema,
                        "texto_pantalla": " ".join(f.split()[:5])})
    escenas.append({"texto": f"¿Tú sabías esto de {tema}? Cuéntame abajo qué te sorprendió más.",
                    "busqueda_visual": tema, "texto_pantalla": "¿Lo sabías?"})
    return {"titulo_trabajo": tema, "angulo": "resumen de datos (sin LLM)", "escenas": escenas}


def escribir_guion(t: Dict, ref: Dict, dossier: Dict, nicho: Dict) -> Dict:
    pmin, pmax = FORMATOS[t["formato"]]["palabras"]
    perfil = cargar_estilo(t["nicho"])
    prompt = (f"NICHO: {nicho.get('nombre')} – {nicho.get('descripcion', '')}\n"
              f"TONO DEL NICHO: {nicho.get('tono', 'cercano')}\n"
              f"FORMATO: {'Short vertical, ritmo muy rápido' if t['formato'] == 'short' else 'video largo con capítulos'}\n"
              f"LARGO: entre {pmin} y {pmax} palabras en total, "
              f"{'5 a 8' if t['formato'] == 'short' else '12 a 25'} escenas.\n\n"
              f"PATRÓN DE LOS CANALES QUE MÁS FUNCIONAN EN ESTE NICHO:\n{estilo.resumen_estilo(perfil) or 'sin perfil todavía'}\n\n"
              f"TEMA: {ref['titulo'] or t['datos'].get('tema')}\n"
              f"INSTRUCCIONES DEL EDITOR: {t['datos'].get('instrucciones', 'ninguna')}\n\n"
              f"INVESTIGACIÓN:\n{dossier['texto'][:6000] or 'sin datos externos'}\n\n"
              f"TRANSCRIPCIÓN DE REFERENCIA (solo inspiración):\n{ref['texto'][:6000] or 'no hay'}")
    g = llm.generar_json(prompt, SISTEMA_GUION, temperatura=0.85)
    if isinstance(g, dict) and g.get("escenas"):
        g["motor"] = llm.proveedor_activo()["nombre"]
        return g
    g = guion_respaldo(ref["titulo"] or t["datos"].get("tema", "este tema"), dossier, pmin)
    g["motor"] = "respaldo-local"
    return g


def producir_original(t: Dict) -> None:
    tid = t["id"]
    nicho = obtener_nicho(t["nicho"])
    fmt = FORMATOS[t["formato"]]
    carpeta = _carpeta(tid)
    vertical = fmt["alto"] > fmt["ancho"]

    ocupado("guionista", "Leyendo el video de referencia" if t["fuente_url"] else "Preparando el tema", tid)
    ref = _referencia(t, carpeta)
    db.actualizar(tid, titulo=(ref["titulo"] or t["titulo"])[:140], etapa="investigando", progreso=10)

    ocupado("guionista", f"Investigando «{ref['titulo'][:60]}»", tid)
    dos = investigacion.dossier(ref["titulo"] or t["datos"].get("tema", ""), ref["texto"], nicho.get("idioma", "es"))
    db.actualizar(tid, etapa="escribiendo guion", progreso=20)

    ocupado("guionista", "Escribiendo el guion con el estilo del nicho", tid)
    g = escribir_guion(t, ref, dos, nicho)
    texto = " ".join(e["texto"] for e in g["escenas"])
    hum = estilo.humanizar(texto, estilo.resumen_estilo(cargar_estilo(t["nicho"])))
    # Si el filtro reescribió, repartir el texto nuevo entre las escenas según su peso original
    if hum["texto"] != texto:
        g["escenas"] = _repartir(hum["texto"], g["escenas"])
    guion = " ".join(e["texto"] for e in g["escenas"])
    libre("guionista", f"Guion de {len(guion.split())} palabras ({g['motor']}), humanidad "
                       f"{hum['antes']['puntaje']} → {hum['despues']['puntaje']}", tid)
    db.fusionar_datos(tid, guion=guion, escenas=g["escenas"], angulo=g.get("angulo", ""),
                      informe_anti_ia=hum, referencia={"titulo": ref["titulo"], "url": ref["url"]},
                      investigacion=[{"titulo": f["titulo"], "url": f["url"]} for f in dos["fuentes"]])
    db.actualizar(tid, etapa="voz", progreso=40)

    ocupado("locutor", "Grabando la locución", tid)
    voz = media.sintetizar_voz(guion, str(carpeta / "voz.mp3"), nicho.get("voz", "es-MX-JorgeNeural"),
                               nicho.get("velocidad_voz", "+4%"))
    pal = subtitulos.palabras_de_audio(voz["ruta"], guion)
    ass = subtitulos.escribir_ass(pal["palabras"], str(carpeta / "subs.ass"), fmt["ancho"], fmt["alto"],
                                  color=nicho.get("color_subtitulos", "amarillo"))
    libre("locutor", f"Voz {voz['motor']}, subtítulos {pal['motor']}", tid, "aviso" if voz["simulada"] else "ok")
    db.actualizar(tid, etapa="montando", progreso=60)

    ocupado("editor", "Planificando planos e insertos según lo que se dice", tid)
    total = media.duracion(voz["ruta"]) + 0.5
    try:
        res = montaje.dirigir(g["escenas"], pal["palabras"], voz["ruta"], ass, str(carpeta / "final.mp4"), carpeta,
                              fmt["ancho"], fmt["alto"], nicho, t["formato"], musica=_musica(nicho))
    except Exception as ex:
        # Si el montaje con insertos falla, sale igual con el montaje simple (un plano por escena)
        libre("editor", f"Montaje con insertos falló ({str(ex)[:120]}); uso el montaje simple", tid, "aviso")
        ocupado("editor", "Montaje simple", tid)
        visuales = []
        for i, e in enumerate(g["escenas"]):
            v = broll.buscar_visual(e.get("busqueda_visual") or e["texto_pantalla"], vertical,
                                    carpeta / f"tarjeta_{i:02d}.jpg", e.get("texto_pantalla") or e["texto"][:50],
                                    fmt["ancho"], fmt["alto"], i, nicho=t["nicho"])
            v["peso"] = max(1, len(e["texto"].split()))
            visuales.append(v)
        media.montar(visuales, voz["ruta"], ass, str(carpeta / "final.mp4"), fmt["ancho"], fmt["alto"],
                     musica=_musica(nicho), trabajo_dir=carpeta)
        res = {"visuales": visuales, "insertos": [], "creditos": sorted({v["credito"] for v in visuales if v.get("credito")}),
               "receta": {}, "motor": "simple", "cortes": len(visuales),
               "cortes_por_min": round(len(visuales) * 60 / total, 1)}
    visuales = res["visuales"]
    final = carpeta / "final.mp4"
    media.miniatura(str(final), str(carpeta / "mini.jpg"), 1.5)
    libre("editor", f"Video montado: {res['cortes']} planos ({res['cortes_por_min']}/min), "
                    f"{len(res['insertos'])} insertos", tid)
    db.actualizar(tid, etapa="empaquetando", progreso=85)

    ocupado("empaquetador", "Decidiendo título, descripción y tags", tid)
    creditos = []
    if ref["url"]:
        creditos.append(f"Inspirado en: {ref['url']}")
    creditos += [f"Fuente: {f['url']}" for f in dos["fuentes"]]
    creditos += [f"Imágenes y video: {c}" for c in res["creditos"]]
    meta = metadatos.generar(guion, nicho, t["formato"], creditos,
                             cargar_estilo(t["nicho"]).get("formulas_titulo", []), g.get("titulo_trabajo", ""))
    libre("empaquetador")

    ocupado("revisor", "Comprobando originalidad y normas", tid)
    rev = cumplimiento.revisar_original(guion, ref["texto"], meta, voz["simulada"], visuales,
                                        int(nicho.get("min_palabras", FORMATOS[t["formato"]]["palabras"][0] * 0.7)),
                                        insertos=res["insertos"])
    libre("revisor", f"Puntaje {rev['puntaje']}/100" + (f", bloqueos: {', '.join(rev['bloqueos'])}" if rev["bloqueos"] else ""),
          tid, "ok" if not rev["bloqueos"] else "aviso")
    db.fusionar_datos(tid, video=str(final), miniatura=str(carpeta / "mini.jpg"), metadatos=meta, revision=rev,
                      visuales=[{k: v.get(k) for k in ("tipo", "credito", "origen", "consulta", "licencia", "recurso_id", "desde", "dur")}
                                for v in visuales],
                      montaje={"insertos": res["insertos"], "receta": res["receta"], "motor": res["motor"],
                               "cortes": res["cortes"], "cortes_por_min": res["cortes_por_min"]},
                      voz=voz["motor"])
    db.actualizar(tid, titulo=meta["titulo"], estado="revision", etapa="listo para revisar", progreso=100,
                  puntaje=rev["puntaje"])


def _repartir(texto: str, escenas: List[Dict]) -> List[Dict]:
    palabras = texto.split()
    pesos = [max(1, len(e["texto"].split())) for e in escenas]
    total, out, i = sum(pesos), [], 0
    for k, (e, p) in enumerate(zip(escenas, pesos)):
        n = len(palabras) - i if k == len(escenas) - 1 else round(len(palabras) * p / total)
        out.append({**e, "texto": " ".join(palabras[i:i + n])})
        i += n
    return [e for e in out if e["texto"]]


def _musica(nicho: Dict):
    from fabrica.ajustes import BASE_DIR
    carpeta = BASE_DIR / "assets" / "musica" / nicho.get("id", "general")
    for base in (carpeta, BASE_DIR / "assets" / "musica"):
        if base.exists():
            pistas = sorted(list(base.glob("*.mp3")) + list(base.glob("*.wav")))
            if pistas:
                import random
                return str(random.choice(pistas))
    return None
