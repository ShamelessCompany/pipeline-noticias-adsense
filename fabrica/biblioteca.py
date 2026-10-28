"""
Biblioteca de recursos: todo el material visual y sonoro que la fábrica puede insertar,
con su licencia y su crédito. Crece sola: cada pieza que se descarga para un video se guarda
aquí y se reutiliza (con preferencia por lo menos usado, para no repetir siempre lo mismo).

Búsqueda:
- Por significado, si está instalado sentence-transformers (modelo CLIP multilingüe, corre en CPU):
  "un emú corriendo por el desierto" encuentra la imagen correcta aunque sus etiquetas estén en inglés.
- Por palabras clave en etiquetas y descripción, siempre disponible.

Solo se admiten licencias que permiten uso comercial. Nada de "NC" (no comercial) ni "ND" (sin derivadas).
"""
import re
import shutil
import sqlite3
import threading
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional

from fabrica.ajustes import BASE_DIR, DB_PATH

BIBLIOTECA_DIR = BASE_DIR / "assets" / "biblioteca"
BIBLIOTECA_DIR.mkdir(parents=True, exist_ok=True)

LICENCIAS_OK = {
    "cc0": "Dominio público (CC0)",
    "pdm": "Dominio público",
    "cc-by": "CC BY (pide crédito)",
    "cc-by-sa": "CC BY-SA (pide crédito)",
    "pexels": "Licencia Pexels",
    "pixabay": "Licencia Pixabay",
    "nasa": "NASA (dominio público)",
    "propio": "Material propio",
    "generado": "Generado por la fábrica",
}
TIPOS = ("video", "imagen", "audio")

_lock = threading.RLock()
_modelos = {"img": None, "txt": None, "estado": "sin cargar"}


def normalizar_licencia(lic: str) -> Optional[str]:
    """Convierte cualquier forma de escribir la licencia a una clave de LICENCIAS_OK, o None si no sirve."""
    l = (lic or "").lower().replace(" ", "-").replace("_", "-")
    if any(x in l for x in ("-nc", "nc-", "noncommercial", "-nd", "nd-", "noderiv")):
        return None
    if l in LICENCIAS_OK:
        return l
    if "cc0" in l or "publicdomain" in l or "public-domain" in l or l == "pd":
        return "cc0"
    if "pdm" in l:
        return "pdm"
    if "by-sa" in l:
        return "cc-by-sa"
    if re.search(r"(^|-)by($|-|\d)", l) or l.startswith("cc-by"):
        return "cc-by"
    for k in ("pexels", "pixabay", "nasa", "propio", "generado"):
        if k in l:
            return k
    return None


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def iniciar() -> None:
    with _lock, _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS recursos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ruta TEXT NOT NULL UNIQUE,
            tipo TEXT NOT NULL,
            subtipo TEXT DEFAULT '',
            origen TEXT DEFAULT '',
            licencia TEXT NOT NULL,
            credito TEXT DEFAULT '',
            url_origen TEXT DEFAULT '',
            etiquetas TEXT DEFAULT '',
            descripcion TEXT DEFAULT '',
            nicho TEXT DEFAULT '',
            embedding BLOB,
            usos INTEGER DEFAULT 0,
            ultimo_uso TEXT DEFAULT '',
            creado TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_recursos_tipo ON recursos(tipo);
        """)


def _sin_tildes(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(ch) != "Mn")


def _tokens(s: str) -> set:
    vacias = {"de", "la", "el", "los", "las", "un", "una", "y", "en", "con", "por", "para", "del", "al",
              "the", "a", "an", "of", "and", "in", "on", "with", "to", "que", "se", "es"}
    return {t for t in re.findall(r"[a-z0-9ñ]{3,}", _sin_tildes(s or "")) if t not in vacias}


# ---------------------------------------------------------------------------
# Búsqueda por significado (opcional)
# ---------------------------------------------------------------------------

def _cargar_modelos() -> bool:
    if _modelos["estado"] == "listo":
        return True
    if _modelos["estado"] == "no disponible":
        return False
    try:
        from sentence_transformers import SentenceTransformer
        _modelos["img"] = SentenceTransformer("clip-ViT-B-32", device="cpu")
        _modelos["txt"] = SentenceTransformer("sentence-transformers/clip-ViT-B-32-multilingual-v1", device="cpu")
        _modelos["estado"] = "listo"
        return True
    except Exception as e:
        print(f"[Biblioteca] Búsqueda por significado no disponible ({e}). Uso palabras clave.")
        _modelos["estado"] = "no disponible"
        return False


def estado_semantico() -> str:
    import importlib.util
    if importlib.util.find_spec("sentence_transformers") is None:
        return "no instalado"
    return "listo" if _modelos["estado"] == "listo" else "instalado"


def _imagen_para_embedding(ruta: str, tipo: str) -> Optional[str]:
    if tipo == "imagen":
        return ruta
    if tipo == "video":
        from fabrica import media
        mini = Path(ruta).with_suffix(".jpg")
        if not mini.exists():
            try:
                media.miniatura(ruta, str(mini), min(1.0, media.duracion(ruta) / 2))
            except Exception:
                return None
        return str(mini)
    return None


def _embedding_imagen(ruta: str):
    if not _cargar_modelos():
        return None
    from PIL import Image
    import numpy as np
    v = _modelos["img"].encode([Image.open(ruta).convert("RGB")], normalize_embeddings=True)[0]
    return np.asarray(v, dtype="float32").tobytes()


def _embedding_texto(texto: str):
    if not _cargar_modelos():
        return None
    import numpy as np
    v = _modelos["txt"].encode([texto], normalize_embeddings=True)[0]
    return np.asarray(v, dtype="float32")


# ---------------------------------------------------------------------------
# Alta y consulta
# ---------------------------------------------------------------------------

def agregar(ruta: str, tipo: str, licencia: str, credito: str = "", origen: str = "", url_origen: str = "",
            etiquetas: str = "", descripcion: str = "", subtipo: str = "", nicho: str = "",
            copiar: bool = False) -> Optional[int]:
    """Registra un recurso. Devuelve su id, o None si la licencia no permite uso comercial."""
    from fabrica.db import ahora
    lic = normalizar_licencia(licencia)
    if not lic:
        print(f"[Biblioteca] Rechazado por licencia «{licencia}»: {ruta}")
        return None
    if tipo not in TIPOS:
        raise ValueError(f"Tipo no válido: {tipo}")
    p = Path(ruta)
    if copiar:
        destino = BIBLIOTECA_DIR / origen.split(":")[0] if origen else BIBLIOTECA_DIR / "propios"
        destino.mkdir(parents=True, exist_ok=True)
        nuevo = destino / p.name
        if nuevo.resolve() != p.resolve():
            shutil.copy(p, nuevo)
        p = nuevo
    emb = None
    try:
        img = _imagen_para_embedding(str(p), tipo)
        emb = _embedding_imagen(img) if img and _modelos["estado"] != "no disponible" else None
    except Exception as e:
        print(f"[Biblioteca] Sin embedding para {p.name}: {e}")
    with _lock, _conn() as c:
        cur = c.execute(
            "INSERT INTO recursos (ruta, tipo, subtipo, origen, licencia, credito, url_origen, etiquetas, descripcion, "
            "nicho, embedding, creado) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(ruta) DO UPDATE SET etiquetas=CASE WHEN instr(recursos.etiquetas, excluded.etiquetas) > 0 "
            "THEN recursos.etiquetas ELSE excluded.etiquetas || ' ' || recursos.etiquetas END",
            (str(p), tipo, subtipo, origen, lic, credito, url_origen, etiquetas.strip(), descripcion.strip(),
             nicho, emb, ahora()))
        if cur.lastrowid:
            return cur.lastrowid
        r = c.execute("SELECT id FROM recursos WHERE ruta=?", (str(p),)).fetchone()
        return r["id"] if r else None


def buscar(consulta: str, tipos=("video", "imagen"), n: int = 5, excluir: Optional[set] = None,
           subtipo: Optional[str] = None, nicho: Optional[str] = None) -> List[Dict]:
    """Los n recursos que mejor encajan con la consulta (texto en cualquier idioma)."""
    excluir = excluir or set()
    q = "SELECT * FROM recursos WHERE tipo IN (%s)" % ",".join("?" * len(tipos))
    args: list = list(tipos)
    if subtipo:
        q += " AND subtipo=?"
        args.append(subtipo)
    with _lock, _conn() as c:
        filas = [dict(r) for r in c.execute(q, args).fetchall()]
    filas = [f for f in filas if f["id"] not in excluir and Path(f["ruta"]).exists()]
    if not filas:
        return []
    qt = _tokens(consulta)
    vec = None
    if any(f["embedding"] for f in filas) and _modelos["estado"] != "no disponible":
        try:
            vec = _embedding_texto(consulta)
        except Exception:
            vec = None
    import numpy as np
    for f in filas:
        texto = f"{f['etiquetas']} {f['descripcion']}"
        ft = _tokens(texto)
        clave = len(qt & ft) / (len(qt) or 1)
        sem = 0.0
        if vec is not None and f["embedding"]:
            sem = float(np.dot(vec, np.frombuffer(f["embedding"], dtype="float32")))
        # La similitud CLIP útil suele ir de 0.2 a 0.35: se reescala para combinarla con las palabras clave
        f["puntaje"] = round(max(clave, (sem - 0.18) * 5 if sem else 0) + (0.1 if nicho and f["nicho"] == nicho else 0)
                             - min(0.3, f["usos"] * 0.03), 3)
        f.pop("embedding", None)
    filas.sort(key=lambda f: f["puntaje"], reverse=True)
    return [f for f in filas[:n] if f["puntaje"] > 0.15]


def marcar_uso(rid: int) -> None:
    from fabrica.db import ahora
    with _lock, _conn() as c:
        c.execute("UPDATE recursos SET usos=usos+1, ultimo_uso=? WHERE id=?", (ahora(), rid))


def listar(tipo: Optional[str] = None, texto: str = "", limite: int = 200) -> List[Dict]:
    if texto:
        return buscar(texto, (tipo,) if tipo else TIPOS, n=limite)
    with _lock, _conn() as c:
        if tipo:
            rows = c.execute("SELECT * FROM recursos WHERE tipo=? ORDER BY id DESC LIMIT ?", (tipo, limite))
        else:
            rows = c.execute("SELECT * FROM recursos ORDER BY id DESC LIMIT ?", (limite,))
        out = [dict(r) for r in rows.fetchall()]
    for f in out:
        f["con_embedding"] = bool(f.pop("embedding", None))
    return out


def obtener(rid: int) -> Optional[Dict]:
    with _lock, _conn() as c:
        r = c.execute("SELECT * FROM recursos WHERE id=?", (rid,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d.pop("embedding", None)
    return d


def borrar(rid: int, borrar_archivo: bool = False) -> None:
    r = obtener(rid)
    with _lock, _conn() as c:
        c.execute("DELETE FROM recursos WHERE id=?", (rid,))
    if r and borrar_archivo and str(BIBLIOTECA_DIR) in r["ruta"] and Path(r["ruta"]).exists():
        Path(r["ruta"]).unlink()


def estadisticas() -> Dict:
    with _lock, _conn() as c:
        por_tipo = {r["tipo"]: r["n"] for r in c.execute("SELECT tipo, COUNT(*) n FROM recursos GROUP BY tipo")}
        por_lic = {r["licencia"]: r["n"] for r in c.execute("SELECT licencia, COUNT(*) n FROM recursos GROUP BY licencia")}
        con_emb = c.execute("SELECT COUNT(*) FROM recursos WHERE embedding IS NOT NULL").fetchone()[0]
    return {"por_tipo": por_tipo, "por_licencia": por_lic, "con_embedding": con_emb,
            "semantica": estado_semantico(), "licencias_validas": LICENCIAS_OK}


def importar_carpeta(carpeta: Path, licencia: str, credito: str = "", nicho: str = "") -> int:
    """Registra todo lo que haya en una carpeta (por ejemplo, assets/biblioteca/propios). Las etiquetas salen del nombre."""
    ext = {".mp4": "video", ".mov": "video", ".webm": "video", ".jpg": "imagen", ".jpeg": "imagen",
           ".png": "imagen", ".webp": "imagen", ".mp3": "audio", ".wav": "audio", ".ogg": "audio"}
    n = 0
    for p in sorted(Path(carpeta).rglob("*")):
        tipo = ext.get(p.suffix.lower())
        if not tipo:
            continue
        etiquetas = re.sub(r"[_\-.]+", " ", p.stem) + " " + " ".join(x.name for x in p.parents
                                                                      if x != Path(carpeta) and Path(carpeta) in x.parents)
        if agregar(str(p), tipo, licencia, credito, origen="propio", etiquetas=etiquetas, nicho=nicho):
            n += 1
    return n


def recalcular_embeddings() -> int:
    """Calcula los embeddings que falten (tras instalar sentence-transformers)."""
    if not _cargar_modelos():
        return 0
    with _lock, _conn() as c:
        filas = [dict(r) for r in c.execute("SELECT id, ruta, tipo FROM recursos WHERE embedding IS NULL AND tipo!='audio'")]
    n = 0
    for f in filas:
        img = _imagen_para_embedding(f["ruta"], f["tipo"])
        if img and Path(img).exists():
            emb = _embedding_imagen(img)
            with _lock, _conn() as c:
                c.execute("UPDATE recursos SET embedding=? WHERE id=?", (emb, f["id"]))
            n += 1
    return n


def exportar_creditos(ids: List[int]) -> List[str]:
    out = []
    for rid in ids:
        r = obtener(rid)
        if r and r["licencia"] not in ("generado", "propio") and r["credito"]:
            linea = f"{r['credito']} ({LICENCIAS_OK.get(r['licencia'], r['licencia'])})"
            if r["url_origen"]:
                linea += f" {r['url_origen']}"
            out.append(linea)
    return sorted(set(out))


iniciar()
