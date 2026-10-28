"""
Agente Publicador: reparte lo aprobado en los horarios de cada nicho y lo sube a su hora.

Modo 'simulado' (por defecto): no sube nada, solo deja anotado qué y cuándo se publicaría.
Modo 'real': usa YouTube Data API v3. Cada nicho publica en el canal de su campo 'canal_youtube'
(por defecto "principal"); los canales se conectan con `python fabrica.py conectar-canal ALIAS`.
"""
from datetime import datetime, timedelta, timezone
from typing import Dict

from fabrica import db
from fabrica.agentes import ocupado, libre, fallo
from fabrica.ajustes import cargar_ajustes, obtener_nicho


def _siguiente_hueco(nicho: Dict) -> str:
    """Primer horario libre del nicho a partir de ahora, sin pasar del cupo diario."""
    horarios = nicho.get("horarios", ["12:00", "19:00"])
    cupo = int(nicho.get("videos_por_dia", 2))
    ocupados = {t["programado_para"] for t in db.listar(limite=500)
                if t["nicho"] == nicho["id"] and t["estado"] in ("programado", "publicado") and t["programado_para"]}
    ahora = datetime.now(timezone.utc).astimezone()
    for dia in range(0, 60):
        fecha = (ahora + timedelta(days=dia)).date()
        del_dia = [o for o in ocupados if o.startswith(fecha.isoformat())]
        if len(del_dia) >= cupo:
            continue
        for h in horarios:
            hh, mm = map(int, h.split(":"))
            slot = datetime(fecha.year, fecha.month, fecha.day, hh, mm, tzinfo=ahora.tzinfo)
            iso = slot.isoformat(timespec="minutes")
            if slot > ahora and iso not in ocupados:
                return iso
    return (ahora + timedelta(hours=1)).isoformat(timespec="minutes")


def programar_aprobados() -> int:
    n = 0
    for t in db.listar("aprobado"):
        if t["datos"].get("campana_id"):
            # Los clips de Whop se suben desde la pestaña Whop, a la cuenta que está inscrita en la campaña
            continue
        nicho = obtener_nicho(t["nicho"])
        slot = _siguiente_hueco(nicho)
        db.actualizar(t["id"], estado="programado", programado_para=slot, etapa=f"sale {slot[:16].replace('T', ' ')}")
        db.registrar("Publicador", f"Programado para {slot[:16].replace('T', ' ')}", t["id"])
        n += 1
    return n


def publicar_pendientes() -> int:
    ahora = datetime.now(timezone.utc).astimezone().isoformat(timespec="minutes")
    n = 0
    for t in db.listar("programado"):
        if t["programado_para"] and t["programado_para"] <= ahora:
            publicar(t)
            n += 1
    return n


def publicar(t: Dict) -> Dict:
    ajustes = cargar_ajustes()
    meta = t["datos"].get("metadatos", {})
    video = t["datos"].get("video")
    from fabrica import whop
    camp = whop.de_trabajo(t)
    canal = (camp and camp["datos"].get("canal_youtube")) or obtener_nicho(t["nicho"]).get("canal_youtube") or "principal"
    ocupado("publicador", f"Publicando «{meta.get('titulo', t['titulo'])[:60]}» en {canal}", t["id"])
    try:
        if ajustes.get("modo_publicacion") == "real":
            res = _subir_youtube(video, meta, ajustes.get("privacidad_publicacion", "private"), canal)
        else:
            res = {"estado": "simulado", "url": "", "mensaje": f"Modo simulado: no se subió nada (canal {canal})"}
        res["canal"] = canal
        db.fusionar_datos(t["id"], publicacion=res)
        db.actualizar(t["id"], estado="publicado", etapa=res["estado"])
        if camp and res.get("url"):
            whop.registrar_envio(camp["id"], res["url"], t["id"], "youtube")
        libre("publicador", f"{res['estado']}: {res.get('url') or res.get('mensaje', '')}", t["id"])
        return res
    except Exception as e:
        if "quotaExceeded" in str(e) or "uploadLimitExceeded" in str(e):
            # Sin cuota hoy: se reintenta mañana a la misma hora en vez de marcarlo como error
            manana = (datetime.now(timezone.utc).astimezone() + timedelta(days=1)).isoformat(timespec="minutes")
            db.actualizar(t["id"], estado="programado", programado_para=manana, etapa="sin cuota de YouTube, reintenta mañana")
            fallo("publicador", "Cuota diaria de YouTube agotada; lo reintento mañana", t["id"])
            return {"estado": "reprogramado", "error": str(e)}
        db.actualizar(t["id"], estado="error", error=str(e)[:500], etapa="falló la subida")
        fallo("publicador", f"Error al subir: {e}", t["id"])
        return {"estado": "error", "error": str(e)}


def _subir_youtube(video: str, meta: Dict, privacidad: str, canal: str) -> Dict:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from fabrica.canales import credenciales

    yt = build("youtube", "v3", credentials=credenciales(canal), cache_discovery=False)
    body = {
        "snippet": {"title": meta.get("titulo", "")[:100], "description": meta.get("descripcion", "")[:4900],
                    "tags": meta.get("tags", []), "categoryId": meta.get("categoria_id", "24"),
                    "defaultLanguage": "es"},
        "status": {"privacyStatus": privacidad, "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": bool(meta.get("contenido_sintetico", False))},
    }
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(video, mimetype="video/mp4", chunksize=8 * 1024 * 1024,
                                                        resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    return {"estado": "publicado", "url": f"https://youtu.be/{resp['id']}", "video_id": resp["id"]}
