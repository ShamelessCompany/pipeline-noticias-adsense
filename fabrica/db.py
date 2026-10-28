"""
Cola de trabajos y bitácora de actividad sobre SQLite (sin servidor, costo cero).

Un "trabajo" es una pieza de contenido en producción. Los tipos son:
- fuente_clip: un video/VOD largo que el Clipper analiza para sacar momentos.
- clip: un momento concreto recortado de una fuente_clip (trabajo hijo).
- original: un video nuevo escrito a partir de un tema o de un video de referencia.

Las campañas de Whop (clipping pagado por vistas) y los enlaces enviados a cada una
viven en las tablas campanas y envios; su lógica está en fabrica/whop.py.
"""
import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fabrica.ajustes import DB_PATH

ESTADOS = ["en_cola", "procesando", "analizado", "revision", "aprobado", "programado", "publicado", "rechazado", "error", "descartado"]

_lock = threading.RLock()


def ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def iniciar() -> None:
    with _lock, _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS trabajos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,
            nicho TEXT NOT NULL,
            formato TEXT NOT NULL DEFAULT 'short',
            titulo TEXT DEFAULT '',
            fuente_url TEXT DEFAULT '',
            estado TEXT NOT NULL DEFAULT 'en_cola',
            etapa TEXT DEFAULT '',
            progreso INTEGER DEFAULT 0,
            padre_id INTEGER,
            datos TEXT DEFAULT '{}',
            error TEXT DEFAULT '',
            puntaje INTEGER DEFAULT 0,
            programado_para TEXT DEFAULT '',
            creado TEXT NOT NULL,
            actualizado TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS eventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            agente TEXT NOT NULL,
            trabajo_id INTEGER,
            nivel TEXT DEFAULT 'info',
            mensaje TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS vistos (
            url TEXT PRIMARY KEY,
            fecha TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS campanas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'activa',
            datos TEXT DEFAULT '{}',
            creado TEXT NOT NULL,
            actualizado TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS envios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campana_id INTEGER NOT NULL,
            trabajo_id INTEGER,
            plataforma TEXT NOT NULL,
            url TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'publicado',
            vistas INTEGER DEFAULT 0,
            pago REAL DEFAULT 0,
            notas TEXT DEFAULT '',
            vistas_actualizadas TEXT DEFAULT '',
            creado TEXT NOT NULL,
            actualizado TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_trabajos_estado ON trabajos(estado);
        CREATE INDEX IF NOT EXISTS idx_envios_campana ON envios(campana_id);
        """)


def _fila(r: sqlite3.Row) -> Dict[str, Any]:
    d = dict(r)
    try:
        d["datos"] = json.loads(d.get("datos") or "{}")
    except Exception:
        d["datos"] = {}
    return d


def crear_trabajo(tipo: str, nicho: str, formato: str = "short", fuente_url: str = "",
                  titulo: str = "", datos: Optional[dict] = None, padre_id: Optional[int] = None) -> int:
    with _lock, _conn() as c:
        cur = c.execute(
            "INSERT INTO trabajos (tipo, nicho, formato, titulo, fuente_url, datos, padre_id, creado, actualizado) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (tipo, nicho, formato, titulo, fuente_url, json.dumps(datos or {}, ensure_ascii=False),
             padre_id, ahora(), ahora())
        )
        return cur.lastrowid


def obtener(trabajo_id: int) -> Optional[Dict[str, Any]]:
    with _lock, _conn() as c:
        r = c.execute("SELECT * FROM trabajos WHERE id=?", (trabajo_id,)).fetchone()
        return _fila(r) if r else None


def listar(estado: Optional[str] = None, limite: int = 200) -> List[Dict[str, Any]]:
    with _lock, _conn() as c:
        if estado:
            rows = c.execute("SELECT * FROM trabajos WHERE estado=? ORDER BY id DESC LIMIT ?", (estado, limite))
        else:
            rows = c.execute("SELECT * FROM trabajos ORDER BY id DESC LIMIT ?", (limite,))
        return [_fila(r) for r in rows.fetchall()]


def actualizar(trabajo_id: int, **campos) -> None:
    if not campos:
        return
    if "datos" in campos and isinstance(campos["datos"], dict):
        campos["datos"] = json.dumps(campos["datos"], ensure_ascii=False)
    campos["actualizado"] = ahora()
    sets = ", ".join(f"{k}=?" for k in campos)
    with _lock, _conn() as c:
        c.execute(f"UPDATE trabajos SET {sets} WHERE id=?", (*campos.values(), trabajo_id))


def fusionar_datos(trabajo_id: int, **nuevos) -> Dict[str, Any]:
    """Mezcla claves nuevas en el JSON 'datos' del trabajo sin pisar el resto."""
    with _lock:
        t = obtener(trabajo_id)
        datos = t["datos"] if t else {}
        datos.update(nuevos)
        actualizar(trabajo_id, datos=datos)
        return datos


def tomar_siguiente() -> Optional[Dict[str, Any]]:
    """Reserva el trabajo en cola más antiguo y lo marca como procesando."""
    with _lock, _conn() as c:
        r = c.execute("SELECT * FROM trabajos WHERE estado='en_cola' ORDER BY id ASC LIMIT 1").fetchone()
        if not r:
            return None
        c.execute("UPDATE trabajos SET estado='procesando', actualizado=? WHERE id=?", (ahora(), r["id"]))
    return obtener(r["id"])


def contar_por_estado() -> Dict[str, int]:
    with _lock, _conn() as c:
        rows = c.execute("SELECT estado, COUNT(*) n FROM trabajos GROUP BY estado").fetchall()
    out = {e: 0 for e in ESTADOS}
    out.update({r["estado"]: r["n"] for r in rows})
    return out


def publicados_hoy(nicho: Optional[str] = None) -> int:
    hoy = ahora()[:10]
    q = "SELECT COUNT(*) FROM trabajos WHERE estado IN ('publicado','programado') AND substr(programado_para,1,10)=?"
    args = [hoy]
    if nicho:
        q += " AND nicho=?"
        args.append(nicho)
    with _lock, _conn() as c:
        return c.execute(q, args).fetchone()[0]


def registrar(agente: str, mensaje: str, trabajo_id: Optional[int] = None, nivel: str = "info") -> None:
    print(f"[{agente}] {mensaje}")
    with _lock, _conn() as c:
        c.execute("INSERT INTO eventos (fecha, agente, trabajo_id, nivel, mensaje) VALUES (?,?,?,?,?)",
                  (ahora(), agente, trabajo_id, nivel, mensaje))


def eventos(desde_id: int = 0, limite: int = 100, trabajo_id: Optional[int] = None) -> List[Dict[str, Any]]:
    with _lock, _conn() as c:
        if trabajo_id:
            rows = c.execute("SELECT * FROM eventos WHERE trabajo_id=? ORDER BY id DESC LIMIT ?", (trabajo_id, limite))
        else:
            rows = c.execute("SELECT * FROM eventos WHERE id>? ORDER BY id DESC LIMIT ?", (desde_id, limite))
        return [dict(r) for r in rows.fetchall()]


def ya_visto(url: str) -> bool:
    with _lock, _conn() as c:
        return c.execute("SELECT 1 FROM vistos WHERE url=?", (url,)).fetchone() is not None


def marcar_visto(url: str) -> None:
    with _lock, _conn() as c:
        c.execute("INSERT OR IGNORE INTO vistos (url, fecha) VALUES (?,?)", (url, ahora()))
