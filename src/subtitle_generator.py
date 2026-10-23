"""
Generador de Subtítulos Cinematográficos (.ASS) para Shorts y TikTok usando Faster-Whisper.
Produce subtítulos con sincronización a nivel de palabra y estilo karaoke de alto impacto.
"""
from pathlib import Path
from faster_whisper import WhisperModel
from src.config import apply_faster_whisper_compat_patch

apply_faster_whisper_compat_patch()

def format_ass_time(seconds: float) -> str:
    """Convierte segundos en formato de tiempo ASS: H:MM:SS.cs"""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = seconds % 60
    centis = int(round((secs - int(secs)) * 100))
    if centis >= 100:
        centis = 99
    return f"{hrs:d}:{mins:02d}:{int(secs):02d}.{centis:02d}"

def generate_karaoke_ass(
    audio_path: str,
    output_ass_path: str,
    model_size: str = "base",
    device: str = "cpu",
    font_name: str = "Arial",
    font_size: int = 76,
    margin_v: int = 440
) -> str:
    """
    Transcribe el audio y genera el archivo .ass con subtítulos dinámicos palabra por palabra.
    """
    out_path = Path(output_ass_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Cargar modelo Whisper optimizado en CPU con int8
    model = WhisperModel(model_size, device=device, compute_type="int8")
    segments, _ = model.transcribe(str(audio_path), word_timestamps=True)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,2,2,40,40,{margin_v},1
Style: Highlight,{font_name},{int(font_size * 1.08)},&H0000FFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,105,105,0,0,1,7,3,2,40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    dialogue_lines = []
    
    # Agrupar palabras en fragmentos cortos de 2 a 3 palabras para máximo ritmo visual
    for segment in segments:
        words = [w for w in segment.words if w.word.strip()]
        if not words:
            continue
            
        i = 0
        while i < len(words):
            chunk = words[i:i+3]
            chunk_start = chunk[0].start
            chunk_end = chunk[-1].end
            
            # Para cada palabra del chunk, generamos un evento donde la palabra activa se resalta
            for target_idx, word in enumerate(chunk):
                w_start = format_ass_time(word.start)
                w_end = format_ass_time(word.end)
                
                # Construir el texto con la palabra actual resaltada en amarillo
                formatted_words = []
                for j, w in enumerate(chunk):
                    w_text = w.word.strip().upper()
                    if j == target_idx:
                        formatted_words.append(r"{\c&H0020FFFF\b1}" + w_text + r"{\r}")
                    else:
                        formatted_words.append(r"{\c&H00FFFFFF}" + w_text + r"{\r}")
                
                phrase = " ".join(formatted_words)
                dialogue_lines.append(
                    f"Dialogue: 0,{w_start},{w_end},Default,,0,0,0,,{phrase}\n"
                )
            i += len(chunk)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(header)
        for line in dialogue_lines:
            f.write(line)

    return str(out_path)
