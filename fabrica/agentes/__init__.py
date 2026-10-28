"""
Los agentes de la fábrica. Cada uno tiene un nombre visible en el panel y reporta
qué está haciendo para que una persona pueda seguir el trabajo en vivo.
"""
import threading
import time
from typing import Dict, Optional

from fabrica import db

AGENTES = {
    "explorador": {"nombre": "Explorador", "rol": "Busca videos nuevos en las fuentes y propone trabajos"},
    "clipper": {"nombre": "Clipper", "rol": "Encuentra los momentos graciosos o interesantes y los recorta"},
    "analista": {"nombre": "Analista de estilo", "rol": "Estudia el estilo y el ritmo de edición de los canales que más funcionan"},
    "guionista": {"nombre": "Guionista", "rol": "Investiga y escribe guiones originales sin muletillas de IA"},
    "locutor": {"nombre": "Locutor", "rol": "Pone voz y subtítulos"},
    "editor": {"nombre": "Editor", "rol": "Monta el video: planos, cifras, fotos e insertos sincronizados, efectos y música"},
    "empaquetador": {"nombre": "Empaquetador", "rol": "Decide título, descripción y tags"},
    "revisor": {"nombre": "Revisor", "rol": "Comprueba las normas de monetización antes de pasar a revisión"},
    "publicador": {"nombre": "Publicador", "rol": "Programa y sube lo aprobado"},
}

_estado: Dict[str, dict] = {k: {"estado": "esperando", "tarea": "", "trabajo_id": None, "desde": time.time(),
                                "hechos": 0} for k in AGENTES}
_lock = threading.Lock()


def ocupado(agente: str, tarea: str, trabajo_id: Optional[int] = None) -> None:
    with _lock:
        _estado[agente].update(estado="trabajando", tarea=tarea, trabajo_id=trabajo_id, desde=time.time())
    db.registrar(AGENTES[agente]["nombre"], tarea, trabajo_id)


def libre(agente: str, resumen: str = "", trabajo_id: Optional[int] = None, nivel: str = "ok") -> None:
    with _lock:
        _estado[agente].update(estado="esperando", tarea="", trabajo_id=None, desde=time.time())
        _estado[agente]["hechos"] += 1
    if resumen:
        db.registrar(AGENTES[agente]["nombre"], resumen, trabajo_id, nivel)


def fallo(agente: str, error: str, trabajo_id: Optional[int] = None) -> None:
    with _lock:
        _estado[agente].update(estado="error", tarea=error[:160], trabajo_id=trabajo_id, desde=time.time())
    db.registrar(AGENTES[agente]["nombre"], error[:500], trabajo_id, "error")


def estado() -> Dict[str, dict]:
    with _lock:
        return {k: {**AGENTES[k], **v} for k, v in _estado.items()}
