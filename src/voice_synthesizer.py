"""
Módulo de Síntesis de Voz Neuronal con Edge-TTS.
Produce audios de alta fidelidad en español con pausas y cadencia natural.
"""
import asyncio
from pathlib import Path
import edge_tts

async def synthesize_voice_async(
    text: str,
    output_audio_path: str,
    voice: str = "es-MX-DaliaNeural",
    rate: str = "+0%",
    pitch: str = "+0Hz"
) -> str:
    """Genera un archivo de audio MP3 usando la API neuronal de Edge-TTS."""
    out_path = Path(output_audio_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(str(out_path))
    return str(out_path)

def synthesize_voice(
    text: str,
    output_audio_path: str,
    voice: str = "es-MX-DaliaNeural",
    rate: str = "+0%",
    pitch: str = "+0Hz"
) -> str:
    """Envoltura sincrónica para synthesize_voice_async."""
    return asyncio.run(synthesize_voice_async(text, output_audio_path, voice, rate, pitch))
