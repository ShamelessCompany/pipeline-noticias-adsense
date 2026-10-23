"""
Entrada Principal CLI para el Pipeline de Noticias Automatizadas.
Permite ejecutar pipelines completos, pasos individuales o lanzar el modo demo.
"""
import sys
import argparse
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

from demo import run_demo
from src.config import OUTPUT_DIR, CONFIG
from src.scraper import capture_screenshot, generate_mock_tweet_html
from src.script_generator import generate_script_with_gemini
from src.voice_synthesizer import synthesize_voice
from src.subtitle_generator import generate_karaoke_ass
from src.video_compositor import assemble_short_video
from src.review_checkpoint import generate_local_review_dashboard, send_discord_notification
from src.youtube_uploader import upload_short_to_youtube

def handle_run(args):
    print(f"\n[Pipeline] Iniciando procesamiento para: {args.topic}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Scrape / Render
    card_path = str(OUTPUT_DIR / "custom_card.png")
    if args.url:
        print(f"[1/5] Capturando URL real: {args.url}")
        capture_screenshot(output_image_path=card_path, url=args.url)
    else:
        print(f"[1/5] Renderizando tarjeta editorial personalizada...")
        html = generate_mock_tweet_html(
            author_name=args.author or "Canal de Noticias",
            author_handle=args.handle or "@noticias_hoy",
            author_avatar="",
            content=args.content or args.topic
        )
        capture_screenshot(output_image_path=card_path, html_content=html)

    # 2. Script
    print(f"[2/5] Generando guion analítico con cumplimiento AdSense...")
    script_data = generate_script_with_gemini(
        news_topic=args.topic,
        source_snippet=args.content or args.topic
    )
    print(f"  Guion ({script_data['word_count']} palabras): {script_data['script'][:80]}...")

    # 3. TTS
    print(f"[3/5] Generando voz neuronal...")
    audio_path = str(OUTPUT_DIR / "custom_voice.mp3")
    synthesize_voice(
        text=script_data["script"],
        output_audio_path=audio_path,
        voice=args.voice or CONFIG["tts"]["voice"]
    )

    # 4. Subtítulos
    print(f"[4/5] Generando subtítulos karaoke sincronizados...")
    ass_path = str(OUTPUT_DIR / "custom_subtitles.ass")
    generate_karaoke_ass(
        audio_path=audio_path,
        output_ass_path=ass_path,
        model_size=CONFIG["subtitles"]["whisper_model"]
    )

    # 5. Composición
    print(f"[5/5] Componiendo video 9:16 para YouTube Shorts...")
    video_path = str(OUTPUT_DIR / "custom_short.mp4")
    assemble_short_video(
        card_image_path=card_path,
        voice_audio_path=audio_path,
        subtitles_ass_path=ass_path,
        output_video_path=video_path,
        broll_video_path=args.broll,
        bgm_audio_path=args.bgm
    )
    print(f"\n✓ Video generado exitosamente: {video_path}")

    # Checkpoint
    dashboard_path = str(OUTPUT_DIR / "custom_checkpoint.html")
    generate_local_review_dashboard(
        video_path=video_path,
        script_data=script_data,
        output_html_path=dashboard_path
    )
    print(f"✓ Dashboard de revisión humana disponible en: {dashboard_path}")

def main():
    parser = argparse.ArgumentParser(
        description="Pipeline de Noticias Automatizadas (Cumplimiento AdSense & YouTube Shorts)"
    )
    subparsers = parser.add_subparsers(dest="command", help="Comandos disponibles")

    # Comando demo
    subparsers.add_parser("demo", help="Ejecuta la demo completa de extremo a extremo")

    # Comando run
    run_parser = subparsers.add_parser("run", help="Procesa una noticia personalizada")
    run_parser.add_argument("--topic", required=True, help="Tema o titular de la noticia")
    run_parser.add_argument("--content", default="", help="Cuerpo o fragmento de la noticia")
    run_parser.add_argument("--url", default=None, help="URL opcional para capturar con Playwright")
    run_parser.add_argument("--author", default="Agencia Central", help="Nombre del autor o fuente")
    run_parser.add_argument("--handle", default="@noticias", help="Handle de la red social")
    run_parser.add_argument("--voice", default=None, help="Nombre de voz Edge-TTS (ej. es-MX-DaliaNeural)")
    run_parser.add_argument("--broll", default=None, help="Ruta a clip de B-roll de fondo opcional")
    run_parser.add_argument("--bgm", default=None, help="Ruta a música de fondo opcional")

    # Comando upload
    upload_parser = subparsers.add_parser("upload", help="Sube un video generado a YouTube")
    upload_parser.add_argument("--video", required=True, help="Ruta al archivo MP4")
    upload_parser.add_argument("--title", required=True, help="Título del video")
    upload_parser.add_argument("--description", default="", help="Descripción")
    upload_parser.add_argument("--privacy", default="unlisted", choices=["public", "private", "unlisted"])

    args = parser.parse_args()

    if args.command == "demo" or args.command is None:
        run_demo()
    elif args.command == "run":
        handle_run(args)
    elif args.command == "upload":
        res = upload_short_to_youtube(
            video_path=args.video,
            title=args.title,
            description=args.description,
            privacy_status=args.privacy
        )
        print(f"Resultado de subida: {res}")

if __name__ == "__main__":
    main()
