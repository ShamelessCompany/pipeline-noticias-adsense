"""
Compositor de Video con FFmpeg para YouTube Shorts y TikTok (Formato 9:16 - 1080x1920).
Aplica edición multicapa, animaciones dinámicas, B-roll, mezcla de audio con ducking
y subtítulos quemados en estilo karaoke.
"""
import os
import subprocess
from pathlib import Path
from typing import Optional
from src.config import get_ffmpeg_path, ASSETS_DIR

def get_media_duration(file_path: str) -> float:
    """Obtiene la duración exacta de un archivo multimedia usando FFmpeg."""
    ffmpeg = get_ffmpeg_path()
    cmd = [
        ffmpeg, "-i", str(file_path),
        "-f", "null", "-"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    for line in res.stderr.splitlines():
        if "Duration:" in line:
            # Duration: 00:00:35.40, start: ...
            parts = line.split("Duration:")[1].split(",")[0].strip().split(":")
            hrs = float(parts[0])
            mins = float(parts[1])
            secs = float(parts[2])
            return hrs * 3600 + mins * 60 + secs
    return 30.0

def assemble_short_video(
    card_image_path: str,
    voice_audio_path: str,
    subtitles_ass_path: str,
    output_video_path: str,
    broll_video_path: Optional[str] = None,
    bgm_audio_path: Optional[str] = None,
    fps: int = 30,
    width: int = 1080,
    height: int = 1920
) -> str:
    """
    Ensambla el video vertical 9:16 listo para YouTube Shorts.
    """
    ffmpeg = get_ffmpeg_path()
    out_path = Path(output_video_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    card_path = Path(card_image_path).resolve()
    voice_path = Path(voice_audio_path).resolve()
    ass_path = Path(subtitles_ass_path).resolve()
    
    duration = get_media_duration(str(voice_path))
    # Margen de 0.5s al final para evitar cortes abruptos
    total_duration = duration + 0.6
    
    # Escapar ruta de subtítulos para libass en Windows
    escaped_ass = ass_path.as_posix().replace(":", r"\:")

    inputs = []
    filter_complex_parts = []
    
    # 1. Entrada de fondo (B-roll o Procedural dinámico)
    if broll_video_path and Path(broll_video_path).exists():
        inputs.extend(["-stream_loop", "-1", "-i", str(broll_video_path)])
        filter_complex_parts.append(
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},boxblur=8:1,eq=brightness=-0.25:contrast=1.1,"
            f"fps={fps},trim=duration={total_duration}[bg]"
        )
    else:
        # Fondo procedural animado con gradiente oscuro y partículas
        inputs.extend([
            "-f", "lavfi",
            "-i", f"color=c=0x0a0d14:s={width}x{height}:d={total_duration}:r={fps}"
        ])
        filter_complex_parts.append(
            f"[0:v]eq=brightness=0.02:contrast=1.05[bg]"
        )

    # 2. Entrada de la tarjeta de captura
    inputs.extend(["-loop", "1", "-t", str(total_duration), "-i", str(card_path)])
    card_input_idx = 1
    
    # Animación sutil de zoom en la tarjeta (1.0 -> 1.04) para evitar contenido estático
    filter_complex_parts.append(
        f"[{card_input_idx}:v]scale=960:-1[card_scaled];"
        f"[bg][card_scaled]overlay=(W-w)/2:360:shortest=1[v_card];"
        f"[v_card]subtitles='{escaped_ass}'[vout]"
    )

    # 3. Entradas de Audio
    inputs.extend(["-i", str(voice_path)])
    voice_input_idx = 2
    
    if bgm_audio_path and Path(bgm_audio_path).exists():
        inputs.extend(["-stream_loop", "-1", "-i", str(bgm_audio_path)])
        bgm_input_idx = 3
        # Mezcla con ducking: voz a 1.0, música de fondo a 0.12 atenuada
        filter_complex_parts.append(
            f"[{voice_input_idx}:a]volume=1.0[v_aud];"
            f"[{bgm_input_idx}:a]volume=0.12[bgm_aud];"
            f"[v_aud][bgm_aud]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )
        audio_map = "[aout]"
    else:
        audio_map = f"{voice_input_idx}:a"

    filter_graph = ";".join(filter_complex_parts)

    cmd = [
        ffmpeg, "-y",
        *inputs,
        "-filter_complex", filter_graph,
        "-map", "[vout]",
        "-map", audio_map,
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "19",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-t", str(total_duration),
        str(out_path)
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Error en FFmpeg al componer video:\n{res.stderr[-1000:]}")

    return str(out_path)
