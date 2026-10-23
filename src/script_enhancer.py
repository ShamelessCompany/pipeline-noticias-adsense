"""
Herramienta de Mejora Contextual de Guiones y Modulación Tonal.
Permite reescribir, pulir y modular la entonación del guion según el contexto
de la noticia (Urgente, Investigativo, Debate, Tecnológico) y optimizarlo para locución.
"""
import os
import re
from typing import Dict, Any, Optional

TONE_PRESETS = {
    "urgente": {
        "name": "Última Hora / Alerta",
        "description": "Ritmo acelerado, ganchos de alta tensión y pausas cortas de impacto.",
        "directive": (
            "Aplica un tono de URGENCIA y NOTICIA DE ÚLTIMA HORA. Las oraciones deben ser ágiles, "
            "con un gancho contundente en los primeros 2 segundos. Usa signos exclamativos y pausas "
            "rápidas para generar adrenalina informativa sin caer en sensacionalismo falso."
        )
    },
    "investigativo": {
        "name": "Misterio / Investigación",
        "description": "Tono analítico, reflexivo, con preguntas retóricas y elipses dramáticas.",
        "directive": (
            "Aplica un tono de INVESTIGACIÓN Y REVELACIÓN. Cuestiona la versión superficial, "
            "utiliza puntos suspensivos (...) para crear pausas de suspenso y destaca detalles ocultos "
            "o consecuencias no evidentes que el público general ignora."
        )
    },
    "polemica": {
        "name": "Debate / Controversia",
        "description": "Contraste fuerte de posturas opuestas para disparar comentarios.",
        "directive": (
            "Aplica un tono de DEBATE Y CONFRONTACIÓN EDITORIAL. Contrasta radicalmente los dos bandos "
            "de la controversia, plantea dilemas morales o económicos y cierra con una pregunta "
            "provocativa diseñada para que la audiencia comente de inmediato."
        )
    },
    "tecnologico": {
        "name": "Futurista / Innovación",
        "description": "Visión de impacto disruptivo, entusiasmo técnico y análisis de futuro.",
        "directive": (
            "Aplica un tono de INNOVACIÓN DISRUPTIVA. Explica por qué este avance cambia las reglas "
            "del juego, compara el 'antes y el después' y transmite el peso histórico del suceso "
            "con vocabulario conciso y apasionante."
        )
    }
}

def refine_script_with_tonality(
    current_script: str,
    tonality: str = "urgente",
    user_instruction: Optional[str] = None,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Mejora y adapta el guion aplicando la tonalidad contextual seleccionada
    e instrucciones manuales del usuario.
    """
    preset = TONE_PRESETS.get(tonality.lower(), TONE_PRESETS["urgente"])
    api_key = api_key or os.getenv("GEMINI_API_KEY")

    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)

            prompt = f"""Guion Actual:
\"\"\"{current_script}\"\"\"

Tonalidad Deseada: {preset['name']}
Directriz de Tono: {preset['directive']}

Instrucción Adicional del Editor:
{user_instruction or "Optimiza la fluidez, la entonación y añade pausas estratégicas (...) para voz humana."}

REGLAS:
- Mantén la duración entre 80 y 130 palabras.
- Aplica signos de puntuación (puntos, comas, signos de interrogación) que guíen la respiración del locutor.
- Cumple con las directrices de AdSense (análisis crítico original, no solo lectura de titulares).
Devuelve ÚNICAMENTE el guion pulido sin preámbulos ni notas explicativas."""

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            refined_text = response.text.strip().strip('"')
            return {
                "script": refined_text,
                "tonality": tonality,
                "preset_name": preset["name"],
                "word_count": len(refined_text.split()),
                "engine": "gemini-2.5-flash"
            }
        except Exception as e:
            print(f"[Script Enhancer] Fallback a motor local por error en Gemini: {e}")

    # Motor local heurístico de mejora tonal
    return refine_script_locally(current_script, tonality, user_instruction)

def refine_script_locally(
    current_script: str,
    tonality: str,
    user_instruction: Optional[str] = None
) -> Dict[str, Any]:
    """Mejora heurística local que inyecta pausas, conectores y énfasis según el tono."""
    cleaned = re.sub(r"\s+", " ", current_script).strip()
    preset = TONE_PRESETS.get(tonality.lower(), TONE_PRESETS["urgente"])

    if tonality == "urgente":
        if not cleaned.startswith("¡"):
            cleaned = "¡Atención a esta noticia de última hora! ... " + cleaned
        cleaned = cleaned.replace(" Pero ", " ... ¡Pero cuidado! ... ")
    elif tonality == "investigativo":
        if not cleaned.startswith("¿"):
            cleaned = "¿Qué hay realmente detrás de este anuncio? ... " + cleaned
        cleaned = cleaned.replace(" La noticia ", " Los documentos revelan que ")
        cleaned = cleaned.replace(" Pero ", " ... Sin embargo, una mirada atenta muestra que ")
    elif tonality == "polemica":
        cleaned = "El mundo está dividido ante lo que acaba de suceder. " + cleaned
        if not "¿Y tú de qué lado estás?" in cleaned:
            cleaned += " ... La pregunta que todos evitan: ¿estás a favor o en contra? Comenta tu postura."
    elif tonality == "tecnologico":
        if not "cambiarlo todo" in cleaned:
            cleaned = "Esto podría cambiar la industria para siempre. ... " + cleaned
        cleaned = cleaned.replace(" noticia ", " salto tecnológico ")

    # Asegurar pausas dramáticas en preguntas y conectores
    cleaned = re.sub(r"(\?|\!)\s*", r"\1 ... ", cleaned)

    return {
        "script": cleaned,
        "tonality": tonality,
        "preset_name": preset["name"],
        "word_count": len(cleaned.split()),
        "engine": "local-tonal-enhancer"
    }
