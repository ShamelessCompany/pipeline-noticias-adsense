"""
Gráficos y efectos de sonido generados por la fábrica (sin derechos de terceros):
- Capas PNG con transparencia: cifra grande, palabra clave, rótulo, cita, lugar y marco para imágenes.
- Efectos de sonido sintetizados con FFmpeg: whoosh, pop, ding, impacto y clic.
El Director de montaje las coloca sobre el video en el momento exacto en que se dicen las cosas.
"""
import textwrap
from typing import Dict, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from fabrica.ajustes import BASE_DIR

SFX_DIR = BASE_DIR / "assets" / "biblioteca" / "sfx"

ACENTOS = {
    "amarillo": (255, 214, 10), "verde": (52, 211, 153), "rosa": (244, 114, 182),
    "celeste": (56, 189, 248), "naranja": (255, 122, 69),
}


def fuente(tam: int, negrita: bool = True):
    nombres = ["arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "Inter-Bold.otf"] if negrita \
        else ["arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf", "Inter-Regular.otf"]
    bases = ["", "/usr/share/fonts/truetype/dejavu/", "/usr/share/fonts/truetype/liberation/",
             "/usr/share/fonts/opentype/inter/", "C:/Windows/Fonts/"]
    for n in nombres:
        for b in bases:
            try:
                return ImageFont.truetype(b + n, tam)
            except Exception:
                continue
    return ImageFont.load_default()


def _lienzo(ancho: int, alto: int) -> Tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _sombra(img: Image.Image, radio: int = 18, opacidad: int = 150) -> Image.Image:
    """Añade una sombra suave detrás de lo que no es transparente."""
    alfa = img.split()[-1]
    sombra = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sombra.putalpha(alfa.point(lambda a: min(opacidad, a)))
    sombra = sombra.filter(ImageFilter.GaussianBlur(radio))
    base = Image.new("RGBA", img.size, (0, 0, 0, 0))
    base.alpha_composite(sombra, (0, radio // 3))
    base.alpha_composite(img)
    return base


def _texto_centrado(d: ImageDraw.ImageDraw, cx: int, y: int, texto: str, f, relleno, borde: int = 0):
    w = d.textlength(texto, font=f)
    d.text((cx - w / 2, y), texto, font=f, fill=relleno, stroke_width=borde, stroke_fill=(0, 0, 0, 255))


def cifra(numero: str, etiqueta: str, dst: str, ancho: int, alto: int, color: str = "amarillo") -> Dict:
    vertical = alto > ancho
    acento = ACENTOS.get(color, ACENTOS["amarillo"])
    img, d = _lienzo(ancho, alto)
    tam = int(ancho * (0.2 if vertical else 0.11))
    lineas = textwrap.wrap(etiqueta.upper(), 18 if vertical else 30)[:2]
    while True:
        fn, fe = fuente(tam), fuente(int(tam * 0.3))
        pw = int(max(d.textlength(numero, font=fn), *(d.textlength(l, font=fe) for l in lineas or [""])) + tam * 0.7)
        if pw <= ancho * 0.92 or tam < 30:
            break
        tam = int(tam * 0.9)
    ph = int(tam * 1.25 + len(lineas) * tam * 0.38 + tam * 0.35)
    cx, y0 = ancho // 2, int(alto * (0.2 if vertical else 0.22))
    d.rounded_rectangle([cx - pw // 2, y0, cx + pw // 2, y0 + ph], radius=int(tam * 0.22), fill=(12, 14, 20, 225))
    d.rectangle([cx - pw // 2, y0 + ph - 10, cx + pw // 2, y0 + ph], fill=acento + (255,))
    _texto_centrado(d, cx, y0 + int(tam * 0.12), numero, fn, acento + (255,))
    for i, l in enumerate(lineas):
        _texto_centrado(d, cx, y0 + int(tam * 1.25) + i * int(tam * 0.38), l, fe, (240, 242, 246, 255))
    _sombra(img).save(dst)
    return {"tipo": "capa", "ruta": dst, "anim": "pop"}


def palabra(texto: str, dst: str, ancho: int, alto: int, color: str = "amarillo") -> Dict:
    vertical = alto > ancho
    acento = ACENTOS.get(color, ACENTOS["amarillo"])
    img, d = _lienzo(ancho, alto)
    lineas = textwrap.wrap(texto.upper(), 12 if vertical else 22)[:2]
    tam = int(ancho * (0.13 if vertical else 0.075))
    f = fuente(tam)
    y = int(alto * (0.3 if vertical else 0.36))
    for i, l in enumerate(lineas):
        w = d.textlength(l, font=f)
        x0 = ancho / 2 - w / 2
        if i == 0:
            d.rectangle([x0 - 24, y + tam * 0.15, x0 + w + 24, y + tam * 1.12], fill=acento + (255,))
            d.text((x0, y), l, font=f, fill=(10, 10, 10, 255))
        else:
            d.text((x0, y), l, font=f, fill=(255, 255, 255, 255), stroke_width=max(4, tam // 14), stroke_fill=(0, 0, 0, 255))
        y += int(tam * 1.15)
    _sombra(img, 12, 120).save(dst)
    return {"tipo": "capa", "ruta": dst, "anim": "pop"}


def rotulo(titulo: str, subtitulo: str, dst: str, ancho: int, alto: int, color: str = "amarillo") -> Dict:
    vertical = alto > ancho
    acento = ACENTOS.get(color, ACENTOS["amarillo"])
    img, d = _lienzo(ancho, alto)
    tam = int(ancho * (0.06 if vertical else 0.032))
    x0 = int(ancho * 0.06)
    while True:
        ft, fs = fuente(tam), fuente(int(tam * 0.62), negrita=False)
        if max(d.textlength(titulo, font=ft), d.textlength(subtitulo, font=fs)) + tam + x0 + 14 <= ancho * 0.94 or tam < 18:
            break
        tam = int(tam * 0.9)
    y0 = int(alto * (0.14 if vertical else 0.72))
    w = int(max(d.textlength(titulo, font=ft), d.textlength(subtitulo, font=fs)) + tam)
    d.rectangle([x0, y0, x0 + 14, y0 + int(tam * 2.1)], fill=acento + (255,))
    d.rectangle([x0 + 14, y0, x0 + 14 + w, y0 + int(tam * 1.25)], fill=(12, 14, 20, 235))
    d.text((x0 + 14 + tam // 2, y0 + int(tam * 0.1)), titulo, font=ft, fill=(255, 255, 255, 255))
    if subtitulo:
        ws = int(d.textlength(subtitulo, font=fs) + tam)
        d.rectangle([x0 + 14, y0 + int(tam * 1.25), x0 + 14 + ws, y0 + int(tam * 2.1)], fill=acento + (240,))
        d.text((x0 + 14 + tam // 2, y0 + int(tam * 1.32)), subtitulo, font=fs, fill=(12, 12, 12, 255))
    _sombra(img, 10, 110).save(dst)
    return {"tipo": "capa", "ruta": dst, "anim": "deslizar"}


def cita(texto: str, autor: str, dst: str, ancho: int, alto: int, color: str = "amarillo") -> Dict:
    vertical = alto > ancho
    acento = ACENTOS.get(color, ACENTOS["amarillo"])
    img, d = _lienzo(ancho, alto)
    tam = int(ancho * (0.055 if vertical else 0.032))
    f, fa = fuente(tam), fuente(int(tam * 0.7), negrita=False)
    lineas = textwrap.wrap(f"«{texto}»", 24 if vertical else 44)[:5]
    pw = int(ancho * (0.84 if vertical else 0.6))
    ph = int(len(lineas) * tam * 1.25 + tam * 2.2)
    x0, y0 = (ancho - pw) // 2, int(alto * (0.18 if vertical else 0.2))
    d.rounded_rectangle([x0, y0, x0 + pw, y0 + ph], radius=28, fill=(245, 245, 240, 240))
    d.rectangle([x0, y0 + 20, x0 + 12, y0 + ph - 20], fill=acento + (255,))
    y = y0 + int(tam * 0.7)
    for l in lineas:
        d.text((x0 + tam, y), l, font=f, fill=(15, 15, 15, 255))
        y += int(tam * 1.25)
    if autor:
        d.text((x0 + tam, y + int(tam * 0.2)), f"— {autor}", font=fa, fill=(80, 80, 80, 255))
    _sombra(img).save(dst)
    return {"tipo": "capa", "ruta": dst, "anim": "pop"}


def lugar(nombre: str, detalle: str, dst: str, ancho: int, alto: int, color: str = "amarillo") -> Dict:
    """Tarjeta de ubicación con un marcador dibujado (sin fuentes de emoji)."""
    vertical = alto > ancho
    acento = ACENTOS.get(color, ACENTOS["amarillo"])
    img, d = _lienzo(ancho, alto)
    tam = int(ancho * (0.075 if vertical else 0.042))
    while True:
        f, fd = fuente(tam), fuente(int(tam * 0.55), negrita=False)
        w = int(max(d.textlength(nombre.upper(), font=f), d.textlength(detalle, font=fd)) + tam * 2.4)
        if w <= ancho * 0.92 or tam < 20:
            break
        tam = int(tam * 0.9)
    h = int(tam * (2.3 if detalle else 1.6))
    x0, y0 = (ancho - w) // 2, int(alto * (0.2 if vertical else 0.18))
    d.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=h // 2, fill=(12, 14, 20, 230))
    # Marcador: círculo + triángulo
    r = int(tam * 0.38)
    cx, cy = x0 + int(tam * 0.95), y0 + h // 2 - r // 3
    d.polygon([(cx - r * 0.8, cy + r * 0.3), (cx + r * 0.8, cy + r * 0.3), (cx, cy + r * 1.7)], fill=acento + (255,))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=acento + (255,))
    d.ellipse([cx - r // 2.5, cy - r // 2.5, cx + r // 2.5, cy + r // 2.5], fill=(12, 14, 20, 255))
    d.text((x0 + int(tam * 1.7), y0 + int(tam * 0.25)), nombre.upper(), font=f, fill=(255, 255, 255, 255))
    if detalle:
        d.text((x0 + int(tam * 1.7), y0 + int(tam * 1.35)), detalle, font=fd, fill=(190, 196, 206, 255))
    _sombra(img).save(dst)
    return {"tipo": "capa", "ruta": dst, "anim": "pop"}


def marco(imagen: str, dst: str, ancho: int, alto: int, escala: float = 0.78,
          posicion: str = "centro", color: str = "blanco") -> Dict:
    """Imagen enmarcada (esquinas redondeadas, borde y sombra) para insertar sobre el video."""
    vertical = alto > ancho
    lado = int(ancho * escala) if vertical else int(alto * escala)
    src = Image.open(imagen).convert("RGB")
    src = ImageOps.contain(src, (lado, lado))
    borde = max(6, lado // 90)
    marco_img = Image.new("RGBA", (src.width + borde * 2, src.height + borde * 2), (0, 0, 0, 0))
    m = Image.new("L", marco_img.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, *marco_img.size], radius=lado // 22, fill=255)
    relleno = (255, 255, 255, 255) if color == "blanco" else ACENTOS.get(color, (255, 255, 255)) + (255,)
    fondo = Image.new("RGBA", marco_img.size, relleno)
    marco_img.paste(fondo, (0, 0), m)
    m2 = Image.new("L", src.size, 0)
    ImageDraw.Draw(m2).rounded_rectangle([0, 0, *src.size], radius=lado // 26, fill=255)
    marco_img.paste(src, (borde, borde), m2)
    img = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    if posicion == "derecha" and not vertical:
        xy = (ancho - marco_img.width - int(ancho * 0.05), (alto - marco_img.height) // 2)
    elif vertical:
        xy = ((ancho - marco_img.width) // 2, int(alto * 0.16))
    else:
        xy = ((ancho - marco_img.width) // 2, (alto - marco_img.height) // 2)
    img.alpha_composite(marco_img, xy)
    _sombra(img, 24, 160).save(dst)
    return {"tipo": "capa", "ruta": dst, "anim": "pop"}


# ---------------------------------------------------------------------------
# Efectos de sonido sintetizados
# ---------------------------------------------------------------------------

SFX = {
    # nombre: (filtro lavfi de la fuente, duración)
    "whoosh": ("anoisesrc=color=pink:amplitude=0.6:d=0.55,highpass=f=300,lowpass=f=5000,"
               "afade=t=in:d=0.3:curve=exp,afade=t=out:st=0.3:d=0.25,volume=0.7", 0.55),
    "pop": ("sine=f=900:d=0.12,afade=t=out:st=0.02:d=0.1:curve=exp,volume=0.8", 0.12),
    "ding": ("sine=f=1318:d=0.7,afade=t=out:st=0.05:d=0.65:curve=exp,volume=0.5", 0.7),
    "impacto": ("sine=f=55:d=0.6,afade=t=out:st=0.05:d=0.55:curve=exp,volume=1.6", 0.6),
    "clic": ("anoisesrc=color=white:amplitude=0.8:d=0.03,highpass=f=2000,afade=t=out:d=0.03,volume=0.6", 0.03),
}


def sfx(nombre: str) -> Optional[str]:
    """Ruta a un efecto de sonido generado (se crea la primera vez y se registra en la biblioteca)."""
    if nombre not in SFX:
        return None
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    dst = SFX_DIR / f"{nombre}.wav"
    if not dst.exists():
        from fabrica.media import _ff
        filtro, dur = SFX[nombre]
        _ff("-f", "lavfi", "-i", filtro, "-t", f"{dur}", "-ar", "48000", "-ac", "2", str(dst))
        from fabrica import biblioteca
        biblioteca.agregar(str(dst), "audio", "generado", origen="generado", etiquetas=f"sfx {nombre}",
                           descripcion=f"Efecto de sonido {nombre}", subtipo="sfx")
    return str(dst)
