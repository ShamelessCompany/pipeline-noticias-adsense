"""
Agente Analista de estilo: mira los videos más vistos de los canales de referencia de un nicho
y guarda el patrón (ganchos, estructura, fórmulas de título) en data/estilos/<nicho>.json.
El Guionista y el Empaquetador leen ese perfil en cada trabajo.
"""
from typing import Dict

from fabrica import estilo, fuentes as yt, db
from fabrica.agentes import ocupado, libre, fallo
from fabrica.ajustes import obtener_nicho, guardar_estilo


def analizar_nicho(nicho_id: str) -> Dict:
    nicho = obtener_nicho(nicho_id)
    canales = nicho.get("canales_referencia", [])
    if not canales:
        raise ValueError("Este nicho no tiene canales de referencia. Añade 2 o 3 en la pestaña Nichos.")
    ocupado("analista", f"Estudiando {len(canales)} canales de {nicho['nombre']}")
    titulos, transcripciones = [], []
    for c in canales:
        try:
            ocupado("analista", f"Leyendo los videos más vistos de {c}")
            top = yt.listar_canal(c, limite=12, populares=True)
            titulos += top
            for v in top[:2]:
                segs = yt.transcripcion_publicada(v["url"])
                if segs:
                    transcripciones.append(yt.texto_plano(segs))
        except Exception as e:
            fallo("analista", f"{c}: {e}")
    titulos.sort(key=lambda x: x["vistas"], reverse=True)
    if not titulos:
        raise RuntimeError("No pude leer ningún canal de referencia")
    perfil = estilo.analizar_estilo(titulos, transcripciones)
    perfil["canales"] = canales
    perfil["actualizado"] = db.ahora()
    guardar_estilo(nicho_id, perfil)
    libre("analista", f"Perfil de estilo de {nicho['nombre']} actualizado ({len(titulos)} títulos, "
                      f"{len(transcripciones)} transcripciones)")
    return perfil


def analizar_edicion(nicho_id: str, videos_por_canal: int = 2) -> Dict:
    """
    Mide cómo editan los videos más vistos de los canales de referencia (cortes, golpes de sonido y,
    con Gemini, qué tipo de plano hay en cada corte) y guarda la receta por formato en el perfil del nicho.
    Los videos se bajan a 360p, se miden y se borran al momento.
    """
    from fabrica import edicion
    from fabrica.ajustes import CACHE_DIR, cargar_estilo
    nicho = obtener_nicho(nicho_id)
    canales = nicho.get("canales_referencia", [])
    if not canales:
        raise ValueError("Este nicho no tiene canales de referencia. Añade 2 o 3 en la pestaña Nichos.")
    muestras: Dict[str, list] = {"short": [], "largo": []}
    for c in canales:
        try:
            ocupado("analista", f"Midiendo la edición de {c}")
            top = yt.listar_canal(c, limite=10, populares=True)
        except Exception as e:
            fallo("analista", f"{c}: {e}")
            continue
        for formato in ("short", "largo"):
            elegidos = [v for v in top if (0 < v["duracion"] <= 70) == (formato == "short") and v["duracion"]][:videos_por_canal]
            for v in elegidos:
                try:
                    ocupado("analista", f"Cortes e insertos de «{v['titulo'][:50]}»")
                    m = edicion.analizar_url(v["url"], CACHE_DIR / "edicion" / nicho_id)
                    m["titulo"] = v["titulo"]
                    muestras[formato].append(m)
                except Exception as e:
                    fallo("analista", f"{v['url']}: {str(e)[:200]}")
    if not muestras["short"] and not muestras["largo"]:
        raise RuntimeError("No pude medir ningún video de los canales de referencia")
    perfil = cargar_estilo(nicho_id) or {}
    perfil["edicion"] = {f: edicion.receta(m, f) for f, m in muestras.items() if m}
    perfil["edicion"]["muestras"] = [{k: m.get(k) for k in ("titulo", "url", "cortes_por_min", "plano_medio_s",
                                                            "golpes_por_min", "planos")}
                                     for ms in muestras.values() for m in ms]
    perfil["edicion"]["actualizado"] = db.ahora()
    guardar_estilo(nicho_id, perfil)
    resumen = ", ".join(f"{f}: {r['cortes_por_min']} cortes/min" for f, r in perfil["edicion"].items()
                        if isinstance(r, dict) and "cortes_por_min" in r)
    libre("analista", f"Receta de edición de {nicho['nombre']} guardada ({resumen})")
    return perfil["edicion"]
