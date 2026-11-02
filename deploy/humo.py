"""Prueba de humo de la plataforma: las piezas nativas que la Fábrica necesita en una máquina nueva.

Comprueba voz (Edge-TTS), transcripción (Faster-Whisper), FFmpeg y Chromium (Playwright).
Pensado para validar una VM nueva (p. ej. Oracle ARM/aarch64) y para la CI en runners ARM.

    python deploy/humo.py
"""
import asyncio
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

FRASE = "Hola, esta es una prueba de la fábrica de contenido."


def paso(nombre, fn):
    try:
        detalle = fn()
        print(f"OK     {nombre}: {detalle}", flush=True)
        return True
    except Exception as e:  # el informe tiene que seguir aunque falle una pieza
        print(f"FALLA  {nombre}: {type(e).__name__}: {e}", flush=True)
        return False


def main() -> int:
    print(f"Plataforma: {platform.system()} {platform.machine()} · Python {platform.python_version()}")
    tmp = Path(tempfile.mkdtemp(prefix="humo_"))
    voz = tmp / "voz.mp3"

    def tts():
        import edge_tts
        asyncio.run(edge_tts.Communicate(FRASE, "es-MX-JorgeNeural").save(str(voz)))
        return f"{voz.stat().st_size} bytes"

    def ffmpeg():
        from src.config import get_ffmpeg_path
        wav = tmp / "voz.wav"
        subprocess.run([get_ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(voz), str(wav)], check=True)
        return f"{wav.stat().st_size} bytes WAV"

    def whisper():
        from faster_whisper import WhisperModel
        modelo = WhisperModel("tiny", device="cpu", compute_type="int8")
        segs, _ = modelo.transcribe(str(voz), language="es", word_timestamps=True)
        texto = " ".join(s.text.strip() for s in segs)
        if "prueba" not in texto.lower():
            raise AssertionError(f"transcripción inesperada: {texto!r}")
        return texto

    def chromium():
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            page = b.new_page(viewport={"width": 1080, "height": 1920})
            page.set_content("<h1 style='font:80px sans-serif'>humo</h1>")
            png = tmp / "captura.png"
            page.screenshot(path=str(png))
            b.close()
        return f"captura {png.stat().st_size} bytes"

    resultados = [paso("Voz Edge-TTS", tts), paso("FFmpeg", ffmpeg),
                  paso("Faster-Whisper (tiny)", whisper), paso("Chromium (Playwright)", chromium)]
    print(f"\n{sum(resultados)}/{len(resultados)} piezas funcionan")
    return 0 if all(resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
