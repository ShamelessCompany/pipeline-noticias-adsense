"""
Título, descripción y tags decididos por el bot a partir del contenido real de la pieza,
siguiendo las fórmulas de título del nicho y sin clickbait engañoso.
"""
import re
from typing import Dict, List

from fabrica import llm
from fabrica.investigacion import palabras_clave

SISTEMA_META = """Eres el encargado de empaquetar videos de YouTube en español.
Con el contenido que te paso, decide título, descripción y tags.
Reglas:
- Título de 40 a 70 caracteres, concreto, que prometa SOLO lo que el video cumple.
- Máximo una palabra en mayúsculas. Sin emojis en el título. Nada de "INCREÍBLE" ni "no vas a creer".
- Descripción: 2-3 frases humanas que resuman sin spoilear el remate, luego una línea en blanco
  y los créditos/fuentes que te paso tal cual. Sin hashtags dentro del texto salvo 3 al final.
- 8 a 15 tags en minúscula, del más específico al más general.
Responde SOLO JSON: {"titulo": "...", "descripcion": "...", "tags": ["..."], "categoria": "..."}"""

CATEGORIAS_YT = {
    "gaming": "20", "videojuegos": "20", "entretenimiento": "24", "comedia": "23", "humor": "23",
    "educacion": "27", "ciencia": "28", "tecnologia": "28", "noticias": "25", "deportes": "17",
    "musica": "10", "historia": "27", "curiosidades": "27", "personas": "22", "blogs": "22",
}


def categoria_id(nombre: str) -> str:
    n = (nombre or "").lower()
    for k, v in CATEGORIAS_YT.items():
        if k in n:
            return v
    return "24"


def generar(contenido: str, nicho: Dict, formato: str, creditos: List[str], formulas: List[str],
            pista_titulo: str = "") -> Dict[str, object]:
    prompt = (f"Nicho: {nicho.get('nombre')} ({nicho.get('descripcion', '')})\n"
              f"Formato: {'YouTube Short vertical' if formato == 'short' else 'video largo horizontal'}\n"
              f"Fórmulas de título que funcionan en este nicho: {formulas or 'libre'}\n"
              f"Idea de título del editor: {pista_titulo or 'ninguna'}\n\n"
              f"CONTENIDO:\n{contenido[:5000]}\n\nCRÉDITOS Y FUENTES:\n" + "\n".join(creditos))
    meta = llm.generar_json(prompt, SISTEMA_META, temperatura=0.7)
    if not isinstance(meta, dict) or not meta.get("titulo"):
        meta = respaldo(contenido, nicho, creditos, pista_titulo)
    meta["titulo"] = re.sub(r"\s+", " ", str(meta["titulo"])).strip()[:100]
    tags = [str(t).strip().lower().lstrip("#") for t in meta.get("tags", []) if str(t).strip()]
    tags += nicho.get("tags_base", [])
    tags = list(dict.fromkeys(t for t in tags if len(t) > 2))
    # YouTube limita a 500 caracteres en total
    finales, total = [], 0
    for t in tags:
        if total + len(t) + 1 > 480:
            break
        finales.append(t)
        total += len(t) + 1
    meta["tags"] = finales
    desc = str(meta.get("descripcion", "")).strip()
    faltan = [c for c in creditos if c and c not in desc]
    if faltan:
        desc += "\n\n" + "\n".join(faltan)
    if formato == "short" and "#shorts" not in desc.lower():
        desc += "\n\n#shorts"
    meta["descripcion"] = desc.strip()
    meta["categoria_id"] = categoria_id(meta.get("categoria") or nicho.get("categoria", ""))
    return meta


def respaldo(contenido: str, nicho: Dict, creditos: List[str], pista: str = "") -> Dict[str, object]:
    claves = palabras_clave(contenido, 8)
    frases = [f.strip() for f in re.split(r"(?<=[.!?])\s+", contenido) if 25 < len(f.strip()) < 90]
    titulo = pista or (frases[0] if frases else f"{nicho.get('nombre', 'Video')}: {' '.join(claves[:3])}")
    resumen = " ".join(frases[:2]) if frases else contenido[:200]
    return {"titulo": titulo, "descripcion": resumen + "\n\n" + "\n".join(creditos),
            "tags": [c.lower() for c in claves] + [nicho.get("nombre", "").lower()],
            "categoria": nicho.get("categoria", "entretenimiento")}
