"""
Demo ejecutable de extremo a extremo del Pipeline de Noticias AdSense.
Ejecuta todo el flujo:
1. Scraper / Renderizado de Noticia en Modo Oscuro (Playwright)
2. Generación de Guion con Filtros Anti-Reutilización (Gemini / Editorial)
3. Síntesis Neuronal en Español (Edge-TTS)
4. Subtítulos Karaoke Palabra por Palabra (Faster-Whisper)
5. Composición Multicapa 9:16 1080x1920 (FFmpeg)
6. Checkpoint de Revisión Humana (Dashboard HTML & Webhook)
"""
import os
import sys
import time
from pathlib import Path

# Añadir raíz al sys.path para importaciones
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

from src.config import OUTPUT_DIR, CONFIG
from src.scraper import capture_screenshot, generate_mock_tweet_html
from src.script_generator import generate_script_with_gemini
from src.voice_synthesizer import synthesize_voice
from src.subtitle_generator import generate_karaoke_ass
from src.video_compositor import assemble_short_video
from src.review_checkpoint import generate_local_review_dashboard
from src.youtube_uploader import upload_short_to_youtube

def run_demo():
    print("=" * 70)
    print("  PIPELINE DE NOTICIAS AUTOMATIZADAS (Cumplimiento AdSense & YPP)  ")
    print("=" * 70)
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    start_time = time.time()

    # 1. Noticia de muestra
    topic = "OpenAI y Google anuncian nuevos estándares abiertos de IA"
    content = (
        "Se acaba de presentar una alianza sin precedentes para estandarizar la interoperabilidad "
        "de modelos generativos. <span class='highlight'>El código abierto y la seguridad serán obligatorios</span> "
        "para todas las plataformas comerciales a partir del próximo trimestre."
    )

    print("\n[Paso 1/6] Capturando tarjeta visual en Modo Oscuro con Playwright...")
    html_card = generate_mock_tweet_html(
        author_name="Tech Dispatch",
        author_handle="@techdispatch_es",
        author_avatar="TD",
        content=content,
        timestamp="Hace 15 minutos",
        metrics={"replies": "3.4K", "reposts": "12.8K", "likes": "89K", "views": "2.4M"}
    )
    card_img_path = str(OUTPUT_DIR / "news_card.png")
    capture_screenshot(
        output_image_path=card_img_path,
        html_content=html_card
    )
    print(f"  -> Tarjeta generada: {card_img_path}")

    print("\n[Paso 2/6] Generando guion editorial con filtros Anti-Reused Content...")
    script_data = generate_script_with_gemini(
        news_topic=topic,
        source_snippet=content
    )
    print(f"  -> Título: {script_data['title']}")
    print(f"  -> Motor: {script_data['engine']}")
    print(f"  -> Conteo de palabras: {script_data['word_count']} palabras")
    print(f"  -> Muestra del guion:\n     \"{script_data['script'][:120]}...\"")

    print("\n[Paso 3/6] Sintetizando audio neuronal en español con Edge-TTS...")
    audio_path = str(OUTPUT_DIR / "voiceover.mp3")
    voice_name = CONFIG["tts"]["voice"]
    synthesize_voice(
        text=script_data["script"],
        output_audio_path=audio_path,
        voice=voice_name
    )
    print(f"  -> Audio generado con voz '{voice_name}': {audio_path}")

    print("\n[Paso 4/6] Generando subtítulos karaoke palabra por palabra con Faster-Whisper...")
    ass_path = str(OUTPUT_DIR / "subtitles.ass")
    # Usar whisper tiny o base según config
    whisper_model = CONFIG["subtitles"].get("whisper_model", "base")
    generate_karaoke_ass(
        audio_path=audio_path,
        output_ass_path=ass_path,
        model_size=whisper_model,
        font_name=CONFIG["subtitles"]["font_name"],
        font_size=CONFIG["subtitles"]["font_size"],
        margin_v=CONFIG["subtitles"]["margin_v"]
    )
    print(f"  -> Subtítulos .ASS sincronizados: {ass_path}")

    print("\n[Paso 5/6] Ensamblando video vertical 9:16 (1080x1920) con FFmpeg...")
    video_path = str(OUTPUT_DIR / "demo_short.mp4")
    assemble_short_video(
        card_image_path=card_img_path,
        voice_audio_path=audio_path,
        subtitles_ass_path=ass_path,
        output_video_path=video_path,
        fps=CONFIG["video"]["fps"],
        width=CONFIG["video"]["width"],
        height=CONFIG["video"]["height"]
    )
    print(f"  -> Video final generado: {video_path}")

    print("\n[Paso 6/6] Creando Checkpoint de Revisión Humana y prueba de subida...")
    dashboard_path = str(OUTPUT_DIR / "checkpoint.html")
    generate_local_review_dashboard(
        video_path=video_path,
        script_data=script_data,
        output_html_path=dashboard_path
    )
    print(f"  -> Dashboard de revisión listo: {dashboard_path}")

    # Simular verificación de publicación
    upload_res = upload_short_to_youtube(
        video_path=video_path,
        title=script_data["title"],
        description=f"{script_data['script']}\n\n#shorts #noticias #tecnologia",
        tags=["#shorts", "#noticias", "#tecnologia", "#ia"]
    )
    print(f"  -> Estado YouTube: {upload_res.get('status')} ({upload_res.get('message', 'OK')})")

    elapsed = time.time() - start_time
    print("\n" + "=" * 70)
    print(f"  DEMO COMPLETADA EXITOSAMENTE EN {elapsed:.1f} SEGUNDOS  ")
    print(f"  Video final: {video_path}")
    print(f"  Revisión:    {dashboard_path}")
    print("=" * 70)

if __name__ == "__main__":
    run_demo()
