"""
Investigación gratuita para videos originales: Wikipedia (sin clave) para contexto y datos,
y la transcripción del video de referencia. El guionista recibe hechos, no texto para copiar.
"""
import re
from typing import Dict, List

import requests

UA = {"User-Agent": "FabricaContenido/1.0 (uso personal)"}


def buscar_wikipedia(consulta: str, idioma: str = "es", n: int = 3) -> List[Dict]:
    try:
        r = requests.get(f"https://{idioma}.wikipedia.org/w/api.php", headers=UA, timeout=20, params={
            "action": "query", "list": "search", "srsearch": consulta, "srlimit": n, "format": "json"})
        r.raise_for_status()
        titulos = [x["title"] for x in r.json()["query"]["search"]]
    except Exception as e:
        print(f"[Investigación] Wikipedia no disponible: {e}")
        return []
    out = []
    for t in titulos:
        try:
            s = requests.get(f"https://{idioma}.wikipedia.org/w/api.php", headers=UA, timeout=20, params={
                "action": "query", "prop": "extracts", "exintro": 0, "explaintext": 1, "exchars": 3000,
                "titles": t, "format": "json"}).json()
            pagina = next(iter(s["query"]["pages"].values()))
            out.append({"titulo": t, "texto": pagina.get("extract", ""),
                        "url": f"https://{idioma}.wikipedia.org/wiki/{t.replace(' ', '_')}"})
        except Exception:
            continue
    return out


def palabras_clave(texto: str, n: int = 6) -> List[str]:
    """Respaldo sin LLM: palabras con mayúscula y términos largos más repetidos."""
    vacias = set("""para como pero porque cuando donde desde hasta sobre entre este esta estos estas
    tiene tienen hacer hace puede pueden también muy más menos todo todos todas cada otro otra
    entonces aquí ahora solo sólo bien mucho mucha muchos algo nada nunca siempre luego antes después""".split())
    cand = re.findall(r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{3,}(?:\s[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{3,})*\b", texto)
    cand += [w for w in re.findall(r"\b[a-záéíóúñ]{7,}\b", texto.lower()) if w not in vacias]
    cuenta: Dict[str, int] = {}
    for c in cand:
        cuenta[c] = cuenta.get(c, 0) + 1
    return [k for k, _ in sorted(cuenta.items(), key=lambda x: -x[1])][:n]


def dossier(tema: str, transcripcion_ref: str = "", idioma: str = "es") -> Dict[str, object]:
    consultas = [tema] + palabras_clave(transcripcion_ref or tema, 2)
    fuentes, vistos = [], set()
    for q in consultas:
        for f in buscar_wikipedia(q, idioma, n=2):
            if f["titulo"] not in vistos and f["texto"]:
                vistos.add(f["titulo"])
                fuentes.append(f)
        if len(fuentes) >= 4:
            break
    return {"tema": tema, "fuentes": fuentes,
            "texto": "\n\n".join(f"[{f['titulo']}] {f['texto'][:1800]}" for f in fuentes)}
