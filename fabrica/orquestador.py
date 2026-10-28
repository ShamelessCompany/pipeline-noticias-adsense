"""
Orquestador: el bucle que mantiene a los agentes trabajando.

- Toma trabajos de la cola uno a uno (la CPU manda; sin GPU, mejor en serie).
- Si el piloto automático está encendido, el Explorador busca material cada N minutos.
- Si la aprobación manual está apagada, lo que supera el umbral y no tiene bloqueos se aprueba solo.
- El Publicador programa lo aprobado y sube lo que ya tocó.
"""
import shutil
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Dict

from fabrica import db
from fabrica.agentes import clipper, guionista, explorador, publicador, fallo
from fabrica.ajustes import cargar_ajustes, TRABAJOS_DIR

_hilo = {"obj": None, "parar": threading.Event(), "ultimo_ciclo": 0.0, "ultima_limpieza": 0.0, "encendido": False}


def procesar(t: Dict) -> None:
    try:
        if t["tipo"] == "fuente_clip":
            clipper.analizar_fuente(t)
        elif t["tipo"] == "clip":
            clipper.producir_clip(t)
        elif t["tipo"] == "original":
            guionista.producir_original(t)
        else:
            raise ValueError(f"Tipo de trabajo desconocido: {t['tipo']}")
        _auto_aprobar(t["id"])
    except Exception as e:
        traceback.print_exc()
        db.actualizar(t["id"], estado="error", error=str(e)[:800])
        agente = "clipper" if "clip" in t["tipo"] else "guionista"
        fallo(agente, f"Trabajo #{t['id']} falló: {e}", t["id"])


def _auto_aprobar(tid: int) -> None:
    aj = cargar_ajustes()
    t = db.obtener(tid)
    if not t or t["estado"] != "revision" or aj.get("aprobacion_manual", True):
        return
    if t["datos"].get("campana_id"):
        # Las campañas de Whop rechazan clips automatizados: siempre los aprueba una persona
        return
    rev = t["datos"].get("revision", {})
    if rev.get("puntaje", 0) >= int(aj.get("umbral_auto_aprobacion", 85)) and not rev.get("bloqueos"):
        db.actualizar(tid, estado="aprobado", etapa="aprobado automáticamente")
        db.registrar("Revisor", f"Aprobado solo (puntaje {rev['puntaje']})", tid)


def paso() -> bool:
    """Una vuelta del bucle. Devuelve True si hizo algo."""
    aj = cargar_ajustes()
    hizo = False
    if aj.get("piloto_automatico") and time.time() - _hilo["ultimo_ciclo"] > aj.get("intervalo_ciclo_min", 60) * 60:
        _hilo["ultimo_ciclo"] = time.time()
        try:
            hizo = bool(explorador.ciclo()) or hizo
        except Exception as e:
            fallo("explorador", str(e))
    t = db.tomar_siguiente()
    if t:
        procesar(t)
        hizo = True
    hizo = bool(publicador.programar_aprobados()) or hizo
    hizo = bool(publicador.publicar_pendientes()) or hizo
    if time.time() - _hilo["ultima_limpieza"] > 3600:
        _hilo["ultima_limpieza"] = time.time()
        limpiar(int(aj.get("dias_retencion", 7)))
    return hizo


def limpiar(dias: int = 7) -> int:
    """
    Libera disco en la VPS: borra los archivos intermedios de lo terminado hace más de N días
    (se quedan final.mp4 y mini.jpg) y los VODs descargados cuyos clips ya salieron todos.
    """
    limite = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat(timespec="seconds")
    liberado = 0
    todos = db.listar(limite=5000)
    for t in todos:
        carpeta = TRABAJOS_DIR / f"{t['id']:05d}"
        if not carpeta.exists():
            continue
        terminado = t["estado"] in ("publicado", "rechazado", "descartado", "error") and t["actualizado"] < limite
        vod_listo = t["tipo"] == "fuente_clip" and t["estado"] == "analizado" and all(
            h["estado"] not in ("en_cola", "procesando") for h in todos if h["padre_id"] == t["id"])
        if not (terminado or vod_listo):
            continue
        for f in carpeta.iterdir():
            if f.name in ("final.mp4", "mini.jpg") and not (t["estado"] in ("rechazado", "descartado") and terminado):
                continue
            liberado += f.stat().st_size if f.is_file() else 0
            shutil.rmtree(f) if f.is_dir() else f.unlink()
    if liberado:
        db.registrar("Orquestador", f"Limpieza: {liberado / 1e9:.2f} GB liberados")
    return liberado


def _bucle() -> None:
    db.registrar("Orquestador", "Trabajador encendido")
    while not _hilo["parar"].is_set():
        try:
            if not paso():
                _hilo["parar"].wait(5)
        except Exception as e:
            traceback.print_exc()
            db.registrar("Orquestador", f"Error en el bucle: {e}", nivel="error")
            _hilo["parar"].wait(10)
    db.registrar("Orquestador", "Trabajador apagado")


def encender() -> None:
    if _hilo["obj"] and _hilo["obj"].is_alive():
        return
    # Lo que quedó a medias por un cierre brusco vuelve a la cola
    for t in db.listar("procesando"):
        db.actualizar(t["id"], estado="en_cola", etapa="reanudado")
    _hilo["parar"].clear()
    _hilo["obj"] = threading.Thread(target=_bucle, daemon=True, name="trabajador")
    _hilo["obj"].start()
    _hilo["encendido"] = True


def apagar() -> None:
    _hilo["parar"].set()
    _hilo["encendido"] = False


def encendido() -> bool:
    return bool(_hilo["obj"] and _hilo["obj"].is_alive() and not _hilo["parar"].is_set())


def forzar_ciclo() -> None:
    _hilo["ultimo_ciclo"] = 0.0
    threading.Thread(target=explorador.ciclo, daemon=True).start()
