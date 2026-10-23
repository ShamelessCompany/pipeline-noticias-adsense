"""
Servidor Web del Estudio Visual para el Pipeline de Noticias AdSense.
Proporciona la interfaz interactiva para cargar enlaces, retocar guiones,
modular tonalidades, probar voces y compilar videos paso a paso o en cascada.
"""
import os
import sys
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory

ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

from src.config import OUTPUT_DIR, CONFIG
from src.scraper import capture_screenshot, generate_mock_tweet_html
from src.script_generator import generate_script_with_gemini
from src.script_enhancer import refine_script_with_tonality, TONE_PRESETS
from src.voice_synthesizer import synthesize_voice
from src.subtitle_generator import generate_karaoke_ass
from src.video_compositor import assemble_short_video
from src.review_checkpoint import generate_local_review_dashboard

app = Flask(__name__, template_folder="templates")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Estado de la sesión actual
SESSION_STATE = {
    "topic": "",
    "content": "",
    "script": "",
    "card_path": str(OUTPUT_DIR / "news_card.png"),
    "audio_path": str(OUTPUT_DIR / "voiceover.mp3"),
    "ass_path": str(OUTPUT_DIR / "subtitles.ass"),
    "video_path": str(OUTPUT_DIR / "demo_short.mp4")
}

@app.route("/")
def index():
    return render_template("index.html", tone_presets=TONE_PRESETS)

@app.route("/media/<path:filename>")
def serve_media(filename):
    """Sirve archivos generados en output/ (imágenes, audios y videos)."""
    return send_from_directory(OUTPUT_DIR, filename)

@app.route("/api/step/capture", methods=["POST"])
def step_capture():
    data = request.json or {}
    url = data.get("url")
    topic = data.get("topic", "Noticia de Tecnología")
    content = data.get("content", "")
    author = data.get("author", "Tech Dispatch")
    handle = data.get("handle", "@techdispatch_es")

    SESSION_STATE["topic"] = topic
    SESSION_STATE["content"] = content

    try:
        out_card = OUTPUT_DIR / "news_card.png"
        if url and url.startswith("http"):
            capture_screenshot(output_image_path=str(out_card), url=url)
        else:
            html = generate_mock_tweet_html(
                author_name=author,
                author_handle=handle,
                author_avatar=author[:2].upper(),
                content=content or topic
            )
            capture_screenshot(output_image_path=str(out_card), html_content=html)

        SESSION_STATE["card_path"] = str(out_card)
        return jsonify({
            "success": True,
            "card_path": str(out_card),
            "card_url": "/media/news_card.png"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/step/generate-script", methods=["POST"])
def step_generate_script():
    data = request.json or {}
    topic = data.get("topic") or SESSION_STATE.get("topic", "Titular de Noticia")
    content = data.get("content") or SESSION_STATE.get("content", "")
    tonality = data.get("tonality", "urgente")

    try:
        res = generate_script_with_gemini(news_topic=topic, source_snippet=content)
        # Aplicar tonalidad solicitada
        refined = refine_script_with_tonality(
            current_script=res["script"],
            tonality=tonality
        )
        SESSION_STATE["script"] = refined["script"]
        return jsonify({
            "success": True,
            "title": res.get("title", topic),
            "script": refined["script"],
            "word_count": refined["word_count"],
            "engine": refined.get("engine", "gemini"),
            "tonality": tonality
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/step/refine-script", methods=["POST"])
def step_refine_script():
    data = request.json or {}
    current_script = data.get("script", "")
    tonality = data.get("tonality", "urgente")
    instruction = data.get("user_instruction")

    if not current_script:
        return jsonify({"success": False, "error": "El guion está vacío"}), 400

    try:
        res = refine_script_with_tonality(
            current_script=current_script,
            tonality=tonality,
            user_instruction=instruction
        )
        SESSION_STATE["script"] = res["script"]
        return jsonify({
            "success": True,
            "script": res["script"],
            "word_count": res["word_count"],
            "preset_name": res["preset_name"]
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/step/synthesize-voice", methods=["POST"])
def step_synthesize_voice():
    data = request.json or {}
    script = data.get("script") or SESSION_STATE.get("script")
    provider = data.get("provider", "edge-tts")
    voice = data.get("voice", "es-MX-DaliaNeural")
    rate = data.get("rate", "+2%")
    pitch = data.get("pitch", "+0Hz")
    reference_audio = data.get("reference_audio")
    voice_id = data.get("voice_id")

    if not script:
        return jsonify({"success": False, "error": "No hay guion para sintetizar"}), 400

    try:
        out_audio = OUTPUT_DIR / "voiceover.mp3"
        synthesize_voice(
            text=script,
            output_audio_path=str(out_audio),
            provider=provider,
            voice=voice,
            rate=rate,
            pitch=pitch,
            reference_audio=reference_audio,
            elevenlabs_voice_id=voice_id
        )
        SESSION_STATE["audio_path"] = str(out_audio)
        SESSION_STATE["script"] = script
        return jsonify({
            "success": True,
            "audio_path": str(out_audio),
            "audio_url": "/media/voiceover.mp3"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/step/assemble-video", methods=["POST"])
def step_assemble_video():
    card_path = SESSION_STATE.get("card_path")
    audio_path = SESSION_STATE.get("audio_path")
    ass_path = OUTPUT_DIR / "subtitles.ass"
    out_video = OUTPUT_DIR / "demo_short.mp4"

    if not Path(card_path).exists():
        return jsonify({"success": False, "error": "Falta capturar la tarjeta (Paso 1)"}), 400
    if not Path(audio_path).exists():
        return jsonify({"success": False, "error": "Falta generar el audio (Paso 3)"}), 400

    try:
        # 1. Subtítulos
        generate_karaoke_ass(
            audio_path=audio_path,
            output_ass_path=str(ass_path),
            model_size=CONFIG["subtitles"]["whisper_model"]
        )
        SESSION_STATE["ass_path"] = str(ass_path)

        # 2. Ensamblado FFmpeg
        assemble_short_video(
            card_image_path=card_path,
            voice_audio_path=audio_path,
            subtitles_ass_path=str(ass_path),
            output_video_path=str(out_video),
            fps=CONFIG["video"]["fps"],
            width=CONFIG["video"]["width"],
            height=CONFIG["video"]["height"]
        )
        SESSION_STATE["video_path"] = str(out_video)

        # 3. Checkpoint HTML
        generate_local_review_dashboard(
            video_path=str(out_video),
            script_data={
                "title": SESSION_STATE.get("topic", "Noticia Editorial"),
                "script": SESSION_STATE.get("script", ""),
                "word_count": len(SESSION_STATE.get("script", "").split())
            },
            output_html_path=str(OUTPUT_DIR / "checkpoint.html")
        )

        return jsonify({
            "success": True,
            "video_path": str(out_video),
            "video_url": "/media/demo_short.mp4",
            "checkpoint_url": "/media/checkpoint.html"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

def run_server(host="127.0.0.1", port=5000, debug=False):
    print("=" * 70)
    print("  ESTUDIO VISUAL DEL PIPELINE DE NOTICIAS ADSENSE")
    print(f"  Disponible en: http://{host}:{port}")
    print("=" * 70)
    app.run(host=host, port=port, debug=debug)

if __name__ == "__main__":
    run_server()
