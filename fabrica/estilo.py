"""
Voz editorial: perfiles de estilo sacados de canales exitosos y un filtro contra
los patrones de escritura típicos de la IA.

El filtro hace tres cosas:
1. Detecta muletillas y estructuras que delatan texto generado ("en el mundo actual",
   "no es solo X, es Y", listas de tres adjetivos, cierres moralizantes...).
2. Mide la variación de largo entre frases: el texto humano alterna frases cortas y largas.
3. Si hay LLM disponible, pide una reescritura que elimine lo detectado; si no, limpia con reglas.
"""
import re
import statistics
from typing import Dict, List, Tuple

from fabrica import llm

# (patrón, motivo, reemplazo o None para eliminar la frase entera)
PATRONES_IA: List[Tuple[str, str, str]] = [
    (r"\ben el (mundo|panorama|escenario) (actual|de hoy|digital)\b", "apertura genérica", ""),
    (r"\ben la era (digital|moderna|actual)\b", "apertura genérica", ""),
    (r"\bhoy en d[ií]a\b", "muletilla temporal", "hoy"),
    (r"\bes importante (destacar|se[ñn]alar|mencionar|recordar) que\b", "relleno", ""),
    (r"\bcabe (destacar|se[ñn]alar|mencionar|resaltar) que\b", "relleno", ""),
    (r"\bvale la pena (destacar|mencionar|se[ñn]alar)( que)?\b", "relleno", ""),
    (r"\ben (conclusi[oó]n|resumen|definitiva),?\s*", "cierre de ensayo", ""),
    (r"\bsin lugar a dudas,?\s*", "énfasis vacío", ""),
    (r"\bsum[eé]rgete\b|\bsumerj[aá]monos\b", "verbo cliché de IA", "entra"),
    (r"\badentr[eé]monos\b|\badentrarnos\b", "verbo cliché de IA", "veamos"),
    (r"\bdesentra[ñn]ar\b|\bdesentra[ñn]emos\b", "verbo cliché de IA", "entender"),
    (r"\bun viaje (fascinante|apasionante|incre[ií]ble)\b", "metáfora gastada", "una historia"),
    (r"\b(fascinante|apasionante) mundo de\b", "metáfora gastada", "tema de"),
    (r"\b(tapiz|crisol) (de|rico)\b", "metáfora gastada", "mezcla de"),
    (r"\bjuega un papel (crucial|fundamental|clave|vital)\b", "frase hecha", "pesa mucho"),
    (r"\bno es solo (\w+(?: \w+){0,3}),? (?:sino que )?es\b", "estructura 'no es solo X, es Y'", None),
    (r"\bno se trata (solo|solamente|únicamente) de\b", "estructura 'no se trata solo de'", None),
    (r"\b(revolucionari[oa]|disruptiv[oa]|innovador[a]?) y (revolucionari[oa]|disruptiv[oa]|innovador[a]?)\b",
     "adjetivos apilados", None),
    (r"\b(crucial|fundamental|esencial|vital)\b", "adjetivo inflado", None),
    (r"\b(robusto|integral|hol[ií]stico|sin precedentes|vers[aá]til)\b", "léxico corporativo", None),
    (r"\bpaisaje\b", "metáfora 'paisaje'", "terreno"),
    (r"\bdesbloquea(r)?\b", "verbo de marketing", "abrir"),
    (r"\bpotencia(r)? (tu|su|el) potencial\b", "frase de marketing", "mejorar"),
    (r"\b¿alguna vez te has preguntado\b", "gancho gastado", None),
    (r"\bimag[ií]nate (por un momento|esto)\b", "gancho gastado", "piensa en esto"),
    (r"\bpero eso no es todo\b", "transición de teletienda", "y hay más"),
    (r"\bdicho esto,?\s*", "transición de ensayo", ""),
    (r"\ben otras palabras,?\s*", "transición de ensayo", ""),
    (r"\bpor [uú]ltimo, pero no menos importante,?\s*", "transición de ensayo", "y "),
    (r"—", "raya larga (muy típica de IA)", ", "),
]

SISTEMA_ANTI_IA = """Eres editor de guiones para YouTube. Reescribes texto para que suene como lo diría
una persona real frente a cámara, no como un ensayo ni como un asistente de IA.
Reglas:
- Frases de largo muy variado. Alguna de tres palabras. Alguna larga.
- Nada de rayas largas (—), ni listas de tres adjetivos, ni "no es solo X, es Y".
- Prohibido: "en el mundo actual", "cabe destacar", "es importante señalar", "sumérgete",
  "fascinante", "crucial", "en conclusión", "sin lugar a dudas", "¿alguna vez te has preguntado".
- Datos concretos antes que adjetivos. Si no hay dato, mejor una imagen concreta.
- Habla a una persona ("tú"), con giros coloquiales del español neutro, sin exagerar.
- No cierres con moraleja. Cierra con una pregunta concreta o con un remate.
- Conserva todos los hechos y nombres. No inventes cifras.
Devuelve solo el texto reescrito."""


def detectar_patrones(texto: str) -> List[Dict[str, str]]:
    hallazgos = []
    for patron, motivo, _ in PATRONES_IA:
        for m in re.finditer(patron, texto, flags=re.IGNORECASE):
            hallazgos.append({"fragmento": m.group(0), "motivo": motivo})
    return hallazgos


def _frases(texto: str) -> List[str]:
    return [f for f in re.split(r"(?<=[.!?¿¡…])\s+", texto.strip()) if f.strip()]


def variacion_frases(texto: str) -> float:
    """Coeficiente de variación del largo de frase. Humano suele estar > 0.45."""
    largos = [len(f.split()) for f in _frases(texto)]
    if len(largos) < 3:
        return 1.0
    media = statistics.mean(largos)
    return round(statistics.pstdev(largos) / media, 2) if media else 0.0


def puntaje_humano(texto: str) -> Dict[str, object]:
    """0-100: cuánto se aleja el texto de los patrones de IA."""
    hallazgos = detectar_patrones(texto)
    var = variacion_frases(texto)
    palabras = max(len(texto.split()), 1)
    densidad = len(hallazgos) / palabras * 100
    puntaje = 100 - min(60, densidad * 12) - (0 if var >= 0.45 else (0.45 - var) * 80)
    return {
        "puntaje": max(0, int(round(puntaje))),
        "variacion_frases": var,
        "hallazgos": hallazgos[:20],
    }


def limpiar_con_reglas(texto: str) -> str:
    out = texto
    for patron, _, reemplazo in PATRONES_IA:
        if reemplazo is None:
            continue
        out = re.sub(patron, reemplazo, out, flags=re.IGNORECASE)
    out = re.sub(r"\s+,", ",", out)
    out = re.sub(r",\s*,", ",", out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    # Reponer mayúscula al inicio de frase tras borrar aperturas
    out = re.sub(r"(^|[.!?]\s+)([a-záéíóúñ])", lambda m: m.group(1) + m.group(2).upper(), out)
    return out


def humanizar(texto: str, contexto_estilo: str = "") -> Dict[str, object]:
    """Pasa el texto por el filtro. Devuelve el texto final y el informe antes/después."""
    antes = puntaje_humano(texto)
    final = texto
    motor = "reglas"
    if antes["puntaje"] < 90 or antes["hallazgos"]:
        detectado = "; ".join(sorted({h["motivo"] for h in antes["hallazgos"]})) or "ritmo plano"
        prompt = (f"Problemas detectados: {detectado}.\n"
                  f"{('Estilo del canal: ' + contexto_estilo) if contexto_estilo else ''}\n\n"
                  f"Texto:\n\"\"\"{texto}\"\"\"")
        reescrito = llm.generar(prompt, SISTEMA_ANTI_IA, temperatura=0.9)
        if reescrito:
            final = reescrito.strip().strip('"').strip()
            motor = llm.proveedor_activo()["nombre"]
    final = limpiar_con_reglas(final)
    despues = puntaje_humano(final)
    return {"texto": final, "antes": antes, "despues": despues, "motor": motor}


# ---------------------------------------------------------------------------
# Perfiles de estilo a partir de canales de referencia
# ---------------------------------------------------------------------------

SISTEMA_ANALISTA = """Eres analista de contenido de YouTube. Te paso títulos con sus vistas y
fragmentos de transcripción de los videos más exitosos de un nicho. Extrae el patrón que repiten.
Responde SOLO con JSON con estas claves:
{
 "tono": "cómo hablan (registro, energía, humor)",
 "ganchos": ["3-5 tipos de apertura que usan en los primeros 5 segundos, con un ejemplo cada uno"],
 "estructura": ["pasos del video en orden"],
 "formulas_titulo": ["4-6 plantillas de título con [variables]"],
 "recursos": ["recursos retóricos que repiten"],
 "evitar": ["cosas que NO hacen"],
 "ritmo": "palabras por minuto aproximadas y cómo cortan",
 "cierre": "cómo terminan los videos"
}"""


def perfil_heuristico(titulos: List[Dict]) -> Dict[str, object]:
    """Respaldo sin LLM: estadísticas simples de los títulos más vistos."""
    if not titulos:
        return {}
    ts = [t["titulo"] for t in titulos]
    n = len(ts)
    return {
        "tono": "directo y conversacional",
        "ganchos": ["Pregunta directa al espectador", "Dato sorprendente en la primera frase"],
        "estructura": ["Gancho", "Contexto en una frase", "Desarrollo con 2-3 giros", "Remate o pregunta"],
        "formulas_titulo": ["[Dato sorprendente] y nadie habla de esto", "Por qué [tema] es [adjetivo]",
                            "Lo que pasó cuando [situación]"],
        "recursos": [],
        "evitar": ["introducciones largas"],
        "ritmo": "rápido",
        "cierre": "pregunta abierta",
        "estadisticas_titulos": {
            "largo_medio": round(sum(len(t) for t in ts) / n),
            "con_numeros": round(sum(bool(re.search(r"\d", t)) for t in ts) / n * 100),
            "con_pregunta": round(sum("?" in t for t in ts) / n * 100),
            "con_mayusculas": round(sum(bool(re.search(r"\b[A-ZÁÉÍÓÚÑ]{4,}\b", t)) for t in ts) / n * 100),
        },
        "motor": "heuristico",
    }


def analizar_estilo(titulos: List[Dict], transcripciones: List[str]) -> Dict[str, object]:
    lista = "\n".join(f"- {t['titulo']} ({t.get('vistas', 0):,} vistas)" for t in titulos[:30])
    trans = "\n\n".join(f"[Video {i + 1}]\n{t[:2500]}" for i, t in enumerate(transcripciones[:4]))
    perfil = llm.generar_json(f"TÍTULOS:\n{lista}\n\nTRANSCRIPCIONES:\n{trans}", SISTEMA_ANALISTA, temperatura=0.3)
    base = perfil_heuristico(titulos)
    if isinstance(perfil, dict):
        base.update(perfil)
        base["motor"] = llm.proveedor_activo()["nombre"]
    base["referencias"] = titulos[:10]
    return base


def resumen_estilo(perfil: Dict) -> str:
    """Texto compacto del perfil para meterlo en los prompts del guionista."""
    if not perfil:
        return ""
    partes = []
    if perfil.get("tono"):
        partes.append(f"Tono: {perfil['tono']}.")
    if perfil.get("ganchos"):
        partes.append("Ganchos que funcionan: " + " | ".join(map(str, perfil["ganchos"][:4])))
    if perfil.get("estructura"):
        partes.append("Estructura: " + " > ".join(map(str, perfil["estructura"][:6])))
    if perfil.get("recursos"):
        partes.append("Recursos: " + ", ".join(map(str, perfil["recursos"][:5])))
    if perfil.get("evitar"):
        partes.append("Evitar: " + ", ".join(map(str, perfil["evitar"][:5])))
    if perfil.get("cierre"):
        partes.append(f"Cierre: {perfil['cierre']}")
    return "\n".join(partes)
