"""
Agente Explorador: recorre las fuentes activas y crea trabajos nuevos.
- Fuentes de clips (con permiso del creador): cada video nuevo pasa a ser un trabajo fuente_clip.
- Fuentes de referencia: sus videos populares inspiran trabajos originales.
- Temas semilla de cada nicho: si no hay fuentes, genera originales a partir de temas sueltos.
Respeta el cupo diario de cada nicho y el máximo de trabajos por ciclo.
"""
import random
from typing import List

from fabrica import db, fuentes as yt
from fabrica.agentes import ocupado, libre, fallo
from fabrica.ajustes import cargar_ajustes, cargar_fuentes, cargar_nichos


def _en_marcha(nicho_id: str) -> int:
    return sum(1 for t in db.listar(limite=500)
               if t["nicho"] == nicho_id and t["estado"] in ("en_cola", "procesando", "revision", "aprobado")
               and t["tipo"] != "fuente_clip")


def ciclo() -> List[int]:
    ajustes = cargar_ajustes()
    tope = int(ajustes.get("max_trabajos_por_ciclo", 3))
    nichos = {n["id"]: n for n in cargar_nichos() if n.get("activo", True)}
    creados: List[int] = []
    ocupado("explorador", "Revisando fuentes y temas")

    for f in cargar_fuentes():
        if len(creados) >= tope:
            break
        if not f.get("activa", True) or f.get("nicho") not in nichos:
            continue
        nicho = nichos[f["nicho"]]
        if _en_marcha(nicho["id"]) >= int(nicho.get("videos_por_dia", 2)) * 2:
            continue
        uso = f.get("uso", "clips")
        if uso == "clips" and not f.get("permite_clips"):
            db.registrar("Explorador", f"Salto {f.get('nombre')}: no tiene marcado 'permite clips'", nivel="aviso")
            continue
        try:
            ocupado("explorador", f"Mirando {f.get('nombre') or f['url']}")
            videos = yt.listar_canal(f["url"], limite=8, populares=(uso == "referencia"))
        except Exception as e:
            fallo("explorador", f"No pude leer {f.get('nombre')}: {e}")
            continue
        for v in videos:
            if len(creados) >= tope or db.ya_visto(v["url"]):
                continue
            dur = v.get("duracion") or 0
            if uso == "clips" and dur and dur < 90:
                continue  # demasiado corto para sacar clips
            db.marcar_visto(v["url"])
            tipo = "fuente_clip" if uso == "clips" else "original"
            formato = nicho.get("formato_clips" if uso == "clips" else "formato", "short")
            tid = db.crear_trabajo(tipo, nicho["id"], formato, fuente_url=v["url"], titulo=v["titulo"],
                                   datos={"origen": f"explorador:{f.get('nombre')}"})
            creados.append(tid)
            db.registrar("Explorador", f"Nuevo {('VOD para clips' if tipo == 'fuente_clip' else 'original')}: "
                                       f"«{v['titulo'][:70]}»", tid)
            break  # uno por fuente y ciclo, para repartir entre canales

    # Temas semilla para nichos sin fuentes con material nuevo
    for nicho in nichos.values():
        if len(creados) >= tope:
            break
        temas = [x for x in nicho.get("temas_semilla", []) if not db.ya_visto(f"tema:{nicho['id']}:{x}")]
        if not temas or _en_marcha(nicho["id"]) >= int(nicho.get("videos_por_dia", 2)):
            continue
        tema = random.choice(temas)
        db.marcar_visto(f"tema:{nicho['id']}:{tema}")
        tid = db.crear_trabajo("original", nicho["id"], nicho.get("formato", "short"), titulo=tema,
                               datos={"tema": tema, "origen": "tema semilla"})
        creados.append(tid)
        db.registrar("Explorador", f"Nuevo original desde tema semilla: «{tema}» ({nicho['nombre']})", tid)

    libre("explorador", f"Ciclo terminado: {len(creados)} trabajos nuevos")
    return creados
