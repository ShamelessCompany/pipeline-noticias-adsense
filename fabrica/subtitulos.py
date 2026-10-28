"""
Transcripción con marcas de tiempo por palabra (faster-whisper, CPU) y subtítulos
.ASS estilo karaoke para cualquier resolución (vertical u horizontal).
Si Whisper no está disponible, reparte el texto conocido a lo largo del audio.
"""
import re
from pathlib import Path
from typing import Dict, List, Optional

from fabrica.ajustes import cargar_ajustes
from fabrica import media

_modelo = {"nombre": None, "obj": None}


def _whisper(nombre: str):
    if _modelo["nombre"] != nombre:
        from src.config import apply_faster_whisper_compat_patch
        apply_faster_whisper_compat_patch()
        from faster_whisper import WhisperModel
        _modelo["obj"] = WhisperModel(nombre, device="cpu", compute_type="int8")
        _modelo["nombre"] = nombre
    return _modelo["obj"]


def transcribir(audio: str, idioma: Optional[str] = None) -> Dict[str, object]:
    """Devuelve {'segmentos': [{inicio, fin, texto}], 'palabras': [{inicio, fin, palabra}], 'motor'}."""
    nombre = cargar_ajustes().get("whisper_modelo", "base")
    modelo = _whisper(nombre)
    segs, _ = modelo.transcribe(str(audio), word_timestamps=True, language=idioma, vad_filter=True)
    segmentos, palabras = [], []
    for s in segs:
        segmentos.append({"inicio": s.start, "fin": s.end, "texto": s.text.strip()})
        for w in s.words or []:
            if w.word.strip():
                palabras.append({"inicio": w.start, "fin": w.end, "palabra": w.word.strip()})
    return {"segmentos": segmentos, "palabras": palabras, "motor": f"whisper-{nombre}"}


def palabras_estimadas(texto: str, dur: float, inicio: float = 0.0) -> List[Dict]:
    """Reparte palabras en el tiempo según su largo (respaldo sin Whisper)."""
    toks = texto.split()
    if not toks:
        return []
    pesos = [len(t) + 2 + (4 if re.search(r"[.!?]$", t) else 0) for t in toks]
    escala = dur / sum(pesos)
    t, out = inicio, []
    for tok, p in zip(toks, pesos):
        d = p * escala
        out.append({"inicio": t, "fin": t + d * 0.92, "palabra": tok})
        t += d
    return out


def palabras_de_audio(audio: str, texto_conocido: str = "", idioma: str = "es") -> Dict[str, object]:
    try:
        r = transcribir(audio, idioma)
        if r["palabras"]:
            return r
    except Exception as e:
        print(f"[Subtítulos] Whisper no disponible ({e}). Uso tiempos estimados.")
    dur = media.duracion(audio)
    return {"segmentos": [{"inicio": 0, "fin": dur, "texto": texto_conocido}],
            "palabras": palabras_estimadas(texto_conocido, dur), "motor": "estimado"}


def _t(seg: float) -> str:
    seg = max(0.0, seg)
    h, rem = divmod(seg, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


ESTILOS_SUB = {
    "amarillo": ("&H00FFFFFF", "&H0000E5FF"),
    "verde": ("&H00FFFFFF", "&H0066FF33"),
    "rosa": ("&H00FFFFFF", "&H00B469FF"),
    "celeste": ("&H00FFFFFF", "&H00FFD24D"),
}


def escribir_ass(palabras: List[Dict], dst: str, ancho: int, alto: int,
                 color: str = "amarillo", por_bloque: int = 3, posicion: float = 0.70) -> str:
    vertical = alto > ancho
    tam = int((78 if vertical else 58) * (ancho / 1080 if vertical else alto / 1080))
    margen_v = int(alto * (1 - posicion)) if vertical else int(alto * 0.08)
    base, resaltado = ESTILOS_SUB.get(color, ESTILOS_SUB["amarillo"])
    cab = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {ancho}
PlayResY: {alto}
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{tam},{base},{resaltado},&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{max(3, tam // 13)},2,2,60,60,{margen_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lineas = []
    n = por_bloque if vertical else por_bloque * 2
    for i in range(0, len(palabras), n):
        bloque = palabras[i:i + n]
        for j, w in enumerate(bloque):
            if j + 1 < len(bloque):
                fin = bloque[j + 1]["inicio"]
            else:
                sig = palabras[i + n]["inicio"] if i + n < len(palabras) else w["fin"]
                fin = sig if sig - w["fin"] < 0.8 else w["fin"] + 0.2
            partes = []
            for k, x in enumerate(bloque):
                txt = re.sub(r"[{}\\]", "", x["palabra"]).upper() if vertical else re.sub(r"[{}\\]", "", x["palabra"])
                if k == j:
                    partes.append(r"{\c" + resaltado + r"\fscx108\fscy108}" + txt + r"{\r}")
                else:
                    partes.append(txt)
            lineas.append(f"Dialogue: 0,{_t(w['inicio'])},{_t(fin)},Default,,0,0,0,,{' '.join(partes)}")
    Path(dst).write_text(cab + "\n".join(lineas) + "\n", encoding="utf-8")
    return dst
