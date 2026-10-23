"""
Módulo Avanzado de Síntesis y Clonación de Voz.
Soporta:
1. Edge-TTS Neuronal (Gratuito, sin GPU, modulación de ritmo y tono).
2. Clonación de Voz Local (Zero-Shot con XTTS-v2 / Coqui / Audio de referencia).
3. ElevenLabs API (Clonación profesional y control de estabilidad/emoción).
4. Preprocesador Expresivo (Inflexiones humanas, pausas de respiración y ritmo).
"""
import os
import re
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any

def optimize_text_for_human_speech(text: str) -> str:
    """
    Preprocesa el texto para que el sintetizador neural aplique inflexiones
    humanas, pausas de respiración y un ritmo menos plano/robótico.
    """
    # Limpiar espacios repetidos
    text = re.sub(r"\s+", " ", text).strip()
    
    # Asegurar pausas naturales después de preguntas iniciales (gancho)
    text = re.sub(r"(\?|\!)\s*", r"\1 ... ", text)
    
    # Enfatizar giros dramáticos con pausas sintácticas
    text = text.replace(" Pero ", " ... Pero ")
    text = text.replace(" Sin embargo, ", " ... Sin embargo, ")
    text = text.replace(" Atención:", " ¡Atención! ...")
    
    return text

async def synthesize_edge_tts(
    text: str,
    output_audio_path: str,
    voice: str = "es-MX-DaliaNeural",
    rate: str = "+2%",
    pitch: str = "+0Hz"
) -> str:
    """Genera audio con Edge-TTS usando preprocesamiento rítmico."""
    import edge_tts
    out_path = Path(output_audio_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    processed_text = optimize_text_for_human_speech(text)
    communicate = edge_tts.Communicate(processed_text, voice, rate=rate, pitch=pitch)
    await communicate.save(str(out_path))
    return str(out_path)

def synthesize_local_clone_xtts(
    text: str,
    output_audio_path: str,
    reference_audio_path: str,
    language: str = "es"
) -> str:
    """
    Clona cualquier voz en local a partir de un archivo de audio de muestra (6 a 10 segundos).
    Requiere la librería Coqui TTS (`pip install TTS`).
    """
    out_path = Path(output_audio_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ref_path = Path(reference_audio_path).resolve()

    if not ref_path.exists():
        raise FileNotFoundError(
            f"No se encontró el audio de referencia para clonación en: {ref_path}\n"
            f"Graba una muestra de 6-10 segundos en formato WAV y colócala en esa ruta."
        )

    try:
        from TTS.api import TTS
        print(f"[Local Voice Clone] Cargando modelo XTTS-v2 para clonar: {ref_path.name}...")
        # Inicializar modelo multilingual XTTS v2
        tts = TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2")
        
        tts.tts_to_file(
            text=text,
            speaker_wav=str(ref_path),
            language=language,
            file_path=str(out_path)
        )
        print(f"[Local Voice Clone] Audio clonado exitosamente en: {out_path}")
        return str(out_path)
    except ImportError:
        raise RuntimeError(
            "Para clonar voces localmente necesitas instalar Coqui TTS:\n"
            "Ejecuta: pip install TTS\n"
            "O mantén el proveedor por defecto 'edge-tts'."
        )

def synthesize_elevenlabs(
    text: str,
    output_audio_path: str,
    voice_id: str,
    api_key: Optional[str] = None,
    stability: float = 0.38,
    similarity_boost: float = 0.85,
    style: float = 0.45
) -> str:
    """
    Genera voz con ElevenLabs permitiendo clonación de voz y modulación emocional.
    Valores bajos de 'stability' (0.3 - 0.45) generan mayor expresividad y dramatismo.
    """
    import requests
    api_key = api_key or os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise ValueError("Se requiere ELEVENLABS_API_KEY en variables de entorno o parámetro.")

    out_path = Path(output_audio_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key
    }
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity_boost,
            "style": style,
            "use_speaker_boost": True
        }
    }

    response = requests.post(url, json=data, headers=headers, timeout=60)
    if response.status_code != 200:
        raise RuntimeError(f"Error de ElevenLabs API ({response.status_code}): {response.text}")

    with open(out_path, "wb") as f:
        f.write(response.content)

    return str(out_path)

def synthesize_voice(
    text: str,
    output_audio_path: str,
    provider: str = "edge-tts",
    voice: str = "es-MX-DaliaNeural",
    rate: str = "+2%",
    pitch: str = "+0Hz",
    reference_audio: Optional[str] = None,
    elevenlabs_voice_id: Optional[str] = None
) -> str:
    """
    Punto de entrada unificado para síntesis de voz del pipeline.
    """
    provider = provider.lower()
    
    if provider == "local-clone" or reference_audio:
        ref = reference_audio or "assets/audio/voice_reference.wav"
        return synthesize_local_clone_xtts(
            text=text,
            output_audio_path=output_audio_path,
            reference_audio_path=ref
        )
    elif provider == "elevenlabs" and elevenlabs_voice_id:
        return synthesize_elevenlabs(
            text=text,
            output_audio_path=output_audio_path,
            voice_id=elevenlabs_voice_id
        )
    else:
        # Por defecto: Edge-TTS optimizado
        return asyncio.run(synthesize_edge_tts(
            text=text,
            output_audio_path=output_audio_path,
            voice=voice,
            rate=rate,
            pitch=pitch
        ))
