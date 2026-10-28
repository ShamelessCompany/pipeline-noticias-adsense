"""
Herramientas de audio y video sobre FFmpeg: duración, mapa de energía del audio
(para encontrar risas y gritos), recortes, reencuadre vertical, voz y montaje final.
"""
import re
import asyncio
import subprocess
import textwrap
from pathlib import Path
from typing import Dict, List, Optional

from src.config import get_ffmpeg_path

FUENTE_TITULOS = "Arial"


def _ff(*args: str, timeout: int = 3600) -> subprocess.CompletedProcess:
    cmd = [get_ffmpeg_path(), "-hide_banner", "-y", *args]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if res.returncode != 0:
        raise RuntimeError("FFmpeg falló:\n" + res.stderr[-1200:])
    return res


def duracion(path: str) -> float:
    res = subprocess.run([get_ffmpeg_path(), "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", res.stderr)
    if not m:
        return 0.0
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def tiene_audio(path: str) -> bool:
    res = subprocess.run([get_ffmpeg_path(), "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    return "Audio:" in res.stderr


def energia_audio(path: str, ventana: float = 1.0, sr: int = 8000) -> List[float]:
    """RMS en dB por ventana. Lee el audio por tramos para aguantar VODs de horas."""
    import numpy as np
    cmd = [get_ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-i", str(path),
           "-vn", "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    paso = int(sr * ventana) * 2
    valores = []
    while True:
        chunk = proc.stdout.read(paso)
        if not chunk:
            break
        a = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
        if a.size == 0:
            break
        rms = float(np.sqrt(np.mean(a ** 2)) + 1e-6)
        valores.append(20 * np.log10(rms / 32768))
    proc.wait()
    return valores


def cortar(src: str, inicio: float, fin: float, dst: str) -> str:
    _ff("-ss", f"{inicio:.2f}", "-i", str(src), "-t", f"{fin - inicio:.2f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k", str(dst))
    return dst


def extraer_audio(src: str, dst: str) -> str:
    _ff("-i", str(src), "-vn", "-ac", "1", "-ar", "16000", str(dst))
    return dst


def _escapar_ruta_filtro(p: str) -> str:
    return Path(p).resolve().as_posix().replace(":", r"\:").replace("'", r"\'")


def _escapar_texto(t: str) -> str:
    return t.replace("\\", "\\\\").replace(":", r"\:").replace("'", "’").replace("%", r"\%")


def reencuadrar(src: str, dst: str, ancho: int, alto: int, ass: Optional[str] = None,
                titulo: str = "", modo: str = "desenfoque", intro_audio: Optional[str] = None) -> str:
    """
    Lleva un clip horizontal a vertical (o al formato pedido):
    - desenfoque: el video completo al centro con el mismo video desenfocado de fondo.
    - recorte: recorta el centro y llena toda la pantalla.
    Añade un título fijo arriba (aporta contexto propio) y subtítulos quemados.
    """
    if modo == "recorte":
        cadena = (f"[0:v]scale={ancho}:{alto}:force_original_aspect_ratio=increase,"
                  f"crop={ancho}:{alto},setsar=1[base]")
    else:
        cadena = (f"[0:v]split=2[a][b];"
                  f"[a]scale={ancho}:{alto}:force_original_aspect_ratio=increase,crop={ancho}:{alto},"
                  f"boxblur=20:2,eq=brightness=-0.18[fondo];"
                  f"[b]scale={ancho}:-2[frente];"
                  f"[fondo][frente]overlay=(W-w)/2:(H-h)/2,setsar=1[base]")
    ultimo = "base"
    if titulo:
        lineas = textwrap.wrap(titulo, width=22 if alto > ancho else 48)[:3]
        tam = 64 if alto > ancho else 52
        y0 = int(alto * 0.09)
        for i, linea in enumerate(lineas):
            cadena += (f";[{ultimo}]drawtext=text='{_escapar_texto(linea)}':font={FUENTE_TITULOS}:"
                       f"fontsize={tam}:fontcolor=white:borderw=6:bordercolor=black:"
                       f"x=(w-text_w)/2:y={y0 + i * int(tam * 1.25)}[t{i}]")
            ultimo = f"t{i}"
    if ass:
        cadena += f";[{ultimo}]subtitles='{_escapar_ruta_filtro(ass)}'[vout]"
        ultimo = "vout"

    entradas = ["-i", str(src)]
    mapa_audio = "0:a?"
    if intro_audio:
        # Narración propia sobre el arranque del clip, bajando el audio original mientras habla
        entradas += ["-i", str(intro_audio)]
        cadena += (";[1:a]aresample=48000,volume=1.4,asplit=2[n1][n2];[n1]apad[sc];"
                   "[0:a]aresample=48000[orig];"
                   "[orig][sc]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=300[duck];"
                   "[duck][n2]amix=inputs=2:duration=first:normalize=0[aout]")
        mapa_audio = "[aout]"
    _ff(*entradas, "-filter_complex", cadena, "-map", f"[{ultimo}]", "-map", mapa_audio,
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-r", "30", "-shortest", str(dst))
    return dst


# ---------------------------------------------------------------------------
# Voz
# ---------------------------------------------------------------------------

def sintetizar_voz(texto: str, dst: str, voz: str = "es-MX-JorgeNeural",
                   velocidad: str = "+4%", tono: str = "+0Hz") -> Dict[str, object]:
    """Edge-TTS gratis. Si no hay internet, genera silencio del largo estimado y lo avisa."""
    try:
        import edge_tts
        from src.voice_synthesizer import optimize_text_for_human_speech

        async def _run():
            com = edge_tts.Communicate(optimize_text_for_human_speech(texto), voz, rate=velocidad, pitch=tono)
            await com.save(str(dst))
        asyncio.run(_run())
        if Path(dst).exists() and Path(dst).stat().st_size > 1000:
            return {"ruta": dst, "motor": f"edge-tts:{voz}", "simulada": False}
    except Exception as e:
        print(f"[Voz] Edge-TTS no disponible ({e}). Uso voz simulada (silencio).")
    segundos = max(3.0, len(texto.split()) / 2.6)
    _ff("-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", f"{segundos:.2f}", "-c:a", "libmp3lame", str(dst))
    return {"ruta": dst, "motor": "simulada", "simulada": True}


# ---------------------------------------------------------------------------
# Montaje de videos originales
# ---------------------------------------------------------------------------

def _segmento_visual(v: Dict, dur: float, ancho: int, alto: int, dst: str, fps: int = 30) -> str:
    """Normaliza una imagen (con zoom lento) o un video de stock a un tramo de duración fija."""
    if v["tipo"] == "video":
        _ff("-stream_loop", "-1", "-i", v["ruta"], "-t", f"{dur:.2f}", "-an",
            "-vf", f"scale={ancho}:{alto}:force_original_aspect_ratio=increase,crop={ancho}:{alto},"
                   f"fps={fps},setsar=1,format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", str(dst))
    else:
        frames = int(dur * fps)
        # Zoom alternado (acercar/alejar) para que no parezca una diapositiva fija
        z = "min(zoom+0.0009,1.12)" if v.get("zoom", "in") == "in" else "if(eq(on,0),1.12,max(zoom-0.0009,1.0))"
        _ff("-loop", "1", "-i", v["ruta"], "-t", f"{dur:.2f}",
            "-vf", f"scale={ancho * 2}:{alto * 2}:force_original_aspect_ratio=increase,crop={ancho * 2}:{alto * 2},"
                   f"zoompan=z='{z}':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={ancho}x{alto}:fps={fps},"
                   f"setsar=1,format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", str(dst))
    return dst


def _filtro_capas(capas: List[Dict], primera_entrada: int, ancho: int, alto: int, entrada: str) -> tuple:
    """Capas PNG a pantalla completa que aparecen en su momento con un fundido y un pequeño movimiento."""
    entradas, cadena, ultimo = [], [], entrada
    for k, c in enumerate(capas):
        a, d = float(c["inicio"]), float(c["dur"])
        idx = primera_entrada + k
        entradas += ["-loop", "1", "-t", f"{d:.2f}", "-i", str(c["ruta"])]
        cadena.append(f"[{idx}:v]scale={ancho}:{alto},format=rgba,fade=t=in:st=0:d=0.15:alpha=1,"
                      f"fade=t=out:st={max(0.0, d - 0.2):.2f}:d=0.2:alpha=1,setpts=PTS-STARTPTS+{a:.2f}/TB[c{k}]")
        if c.get("anim") == "deslizar":
            pos = f"x='if(lt(t-{a:.2f},0.25),-W*(1-(t-{a:.2f})/0.25),0)':y=0"
        else:
            pos = f"x=0:y='if(lt(t-{a:.2f},0.18),{int(alto * 0.03)}*(1-(t-{a:.2f})/0.18),0)'"
        cadena.append(f"[{ultimo}][c{k}]overlay={pos}:eof_action=pass:enable='between(t,{a:.2f},{a + d:.2f})'[o{k}]")
        ultimo = f"o{k}"
    return entradas, cadena, ultimo


def montar(visuales: List[Dict], audio: str, ass: Optional[str], dst: str, ancho: int, alto: int,
           musica: Optional[str] = None, trabajo_dir: Optional[Path] = None, capas: Optional[List[Dict]] = None,
           sfx: Optional[List[Dict]] = None, zooms: Optional[List[Dict]] = None) -> str:
    """
    visuales: [{tipo: imagen|video, ruta, peso | dur}] en orden. Si traen 'dur' se usa tal cual;
    si no, el tiempo total (duración del audio) se reparte según 'peso'.
    capas: [{ruta (PNG RGBA), inicio, dur, anim}] gráficos encima del video, bajo los subtítulos.
    sfx: [{ruta, inicio, volumen}] efectos que se mezclan con la voz.
    zooms: [{inicio, dur, escala}] golpes de zoom sobre el plano de fondo.
    """
    trabajo_dir = Path(trabajo_dir or Path(dst).parent)
    total = duracion(audio) + 0.5
    pesos = [float(v.get("peso", 1.0)) for v in visuales] or [1.0]
    suma = sum(pesos)
    tramos = []
    for i, v in enumerate(visuales):
        d = float(v["dur"]) if v.get("dur") else max(1.5, total * pesos[i] / suma)
        tramos.append(_segmento_visual(v, max(0.4, d), ancho, alto, str(trabajo_dir / f"tramo_{i:02d}.mp4")))
    lista = trabajo_dir / "tramos.txt"
    lista.write_text("".join(f"file '{Path(t).resolve().as_posix()}'\n" for t in tramos), encoding="utf-8")
    base = trabajo_dir / "visual.mp4"
    _ff("-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(base))

    entradas = ["-i", str(base), "-i", str(audio)]
    siguiente = 2
    cadena = []
    ultimo = "0:v"
    if zooms:
        cond = "+".join(f"between(t,{z['inicio']:.2f},{z['inicio'] + z['dur']:.2f})*{z.get('escala', 1.08) - 1:.3f}"
                        for z in zooms)
        cadena.append(f"[0:v]scale=w='trunc(iw*(1+{cond})/2)*2':h='trunc(ih*(1+{cond})/2)*2':eval=frame,"
                      f"crop={ancho}:{alto},setsar=1[zm]")
        ultimo = "zm"
    if capas:
        e, c, ultimo = _filtro_capas(capas, siguiente, ancho, alto, ultimo)
        entradas += e
        cadena += c
        siguiente += len(capas)
    if ass:
        cadena.append(f"[{ultimo}]subtitles='{_escapar_ruta_filtro(ass)}'[v]")
    else:
        cadena.append(f"[{ultimo}]null[v]")

    mezcla = ["[voz]"]
    cadena.append("[1:a]aresample=48000,aformat=channel_layouts=stereo[voz0]")
    if musica and Path(musica).exists():
        entradas += ["-stream_loop", "-1", "-i", str(musica)]
        cadena.append(f"[voz0]asplit=2[voz][vsc];[{siguiente}:a]aresample=48000,aformat=channel_layouts=stereo,"
                      f"volume=0.25[m];[m][vsc]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=400[md]")
        mezcla.append("[md]")
        siguiente += 1
    else:
        cadena.append("[voz0]anull[voz]")
    for k, s in enumerate(sfx or []):
        ms = int(float(s["inicio"]) * 1000)
        entradas += ["-i", str(s["ruta"])]
        cadena.append(f"[{siguiente}:a]aresample=48000,aformat=channel_layouts=stereo,"
                      f"volume={float(s.get('volumen', 0.5)):.2f},adelay={ms}|{ms}[s{k}]")
        mezcla.append(f"[s{k}]")
        siguiente += 1
    if len(mezcla) > 1:
        cadena.append(f"{''.join(mezcla)}amix=inputs={len(mezcla)}:duration=first:normalize=0[a]")
    else:
        cadena.append("[voz]anull[a]")
    _ff(*entradas, "-filter_complex", ";".join(cadena), "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.2f}", str(dst))
    return dst


def miniatura(video: str, dst: str, segundo: float = 1.0) -> str:
    _ff("-ss", f"{segundo:.2f}", "-i", str(video), "-frames:v", "1", "-vf", "scale=480:-2", str(dst))
    return dst
