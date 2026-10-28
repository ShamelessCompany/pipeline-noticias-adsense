"""
Sala de control de la Fábrica de Contenido.
Interfaz web local para ver a los agentes trabajar, revisar y aprobar piezas,
y configurar nichos, fuentes y modelos. Arranca con:  python fabrica.py panel
"""
import hmac
import os
import sys
import threading
import time
from pathlib import Path

from flask import Flask, Response, jsonify, request, render_template, send_from_directory, abort

ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

from fabrica import db, llm, estilo, orquestador, canales, biblioteca, whop
from fabrica.agentes import estado as estado_agentes, analista, publicador
from fabrica.ajustes import (BASE_DIR, TRABAJOS_DIR, cargar_ajustes, guardar_ajustes, cargar_nichos,
                             guardar_nichos, cargar_fuentes, guardar_fuentes, cargar_estilo, FORMATOS)

app = Flask(__name__, template_folder="templates", static_folder="static")
db.iniciar()


@app.before_request
def _proteger():
    """Si PANEL_CLAVE está definida (en .env), el panel pide usuario y contraseña."""
    clave = os.getenv("PANEL_CLAVE", "")
    if not clave:
        return None
    auth = request.authorization
    usuario = os.getenv("PANEL_USUARIO", "admin")
    if auth and hmac.compare_digest(auth.username or "", usuario) and hmac.compare_digest(auth.password or "", clave):
        return None
    return Response("Acceso restringido", 401, {"WWW-Authenticate": 'Basic realm="Fabrica"'})

CLAVES = ["GEMINI_API_KEY", "OPENCODE_API_KEY", "PEXELS_API_KEY", "PIXABAY_API_KEY"]


def _resumen(t: dict) -> dict:
    d = t["datos"]
    return {
        "id": t["id"], "tipo": t["tipo"], "nicho": t["nicho"], "formato": t["formato"],
        "titulo": t["titulo"], "estado": t["estado"], "etapa": t["etapa"], "progreso": t["progreso"],
        "puntaje": t["puntaje"], "error": t["error"], "padre_id": t["padre_id"],
        "programado_para": t["programado_para"], "creado": t["creado"], "actualizado": t["actualizado"],
        "miniatura": f"/media/trabajo/{t['id']}/mini.jpg" if d.get("miniatura") else "",
        "bloqueos": (d.get("revision") or {}).get("bloqueos", []),
        "campana_id": d.get("campana_id"),
    }


@app.route("/")
def inicio():
    return render_template("fabrica.html")


@app.route("/media/trabajo/<int:tid>/<path:archivo>")
def media_trabajo(tid, archivo):
    carpeta = TRABAJOS_DIR / f"{tid:05d}"
    if not carpeta.exists():
        abort(404)
    return send_from_directory(carpeta, archivo)


@app.route("/api/estado")
def api_estado():
    aj = cargar_ajustes()
    activos = [_resumen(t) for t in db.listar("procesando", 5)]
    return jsonify({
        "conteos": db.contar_por_estado(),
        "agentes": estado_agentes(),
        "trabajador": orquestador.encendido(),
        "piloto_automatico": aj.get("piloto_automatico"),
        "aprobacion_manual": aj.get("aprobacion_manual"),
        "modo_publicacion": aj.get("modo_publicacion"),
        "llm": llm.proveedor_activo(),
        "en_curso": activos,
        "whop_listos": sum(1 for t in db.listar("aprobado") if t["datos"].get("campana_id")),
    })


@app.route("/api/eventos")
def api_eventos():
    return jsonify(db.eventos(int(request.args.get("desde", 0)), int(request.args.get("limite", 80))))


@app.route("/api/trabajos")
def api_trabajos():
    return jsonify([_resumen(t) for t in db.listar(request.args.get("estado"), int(request.args.get("limite", 300)))])


@app.route("/api/trabajos/<int:tid>")
def api_trabajo(tid):
    t = db.obtener(tid)
    if not t:
        abort(404)
    d = dict(t["datos"])
    for k in ("segmentos", "energia_resumen"):
        d.pop(k, None)
    out = _resumen(t)
    out["datos"] = d
    out["fuente_url"] = t["fuente_url"]
    out["video_url"] = f"/media/trabajo/{tid}/final.mp4" if d.get("video") else ""
    out["eventos"] = db.eventos(trabajo_id=tid, limite=60)
    out["hijos"] = [_resumen(h) for h in db.listar(limite=500) if h["padre_id"] == tid]
    return jsonify(out)


@app.route("/api/trabajos", methods=["POST"])
def api_nuevo():
    b = request.json or {}
    tipo = b.get("tipo")
    nicho = b.get("nicho") or (cargar_nichos() or [{"id": "general"}])[0]["id"]
    formato = b.get("formato") if b.get("formato") in FORMATOS else "short"
    url = (b.get("url") or "").strip()
    if tipo == "clip":
        if not url:
            return jsonify({"error": "Falta la URL del video o VOD"}), 400
        tid = db.crear_trabajo("fuente_clip", nicho, formato, fuente_url=url, titulo=url,
                               datos={"permiso_manual": bool(b.get("permiso")), "origen": "manual"})
    elif tipo == "original":
        tema = (b.get("tema") or "").strip()
        if not url and not tema:
            return jsonify({"error": "Pon un tema o la URL de un video de referencia"}), 400
        tid = db.crear_trabajo("original", nicho, formato, fuente_url=url, titulo=tema or url,
                               datos={"tema": tema, "instrucciones": b.get("instrucciones", ""), "origen": "manual"})
    else:
        return jsonify({"error": "Tipo no válido"}), 400
    if url:
        db.marcar_visto(url)
    db.registrar("Panel", f"Trabajo creado a mano ({tipo})", tid)
    return jsonify({"id": tid})


@app.route("/api/trabajos/<int:tid>/<accion>", methods=["POST"])
def api_accion(tid, accion):
    t = db.obtener(tid)
    if not t:
        abort(404)
    b = request.json or {}
    if accion in ("aprobar", "publicar"):
        if b.get("metadatos"):
            meta = {**t["datos"].get("metadatos", {}), **b["metadatos"]}
            db.fusionar_datos(tid, metadatos=meta)
            db.actualizar(tid, titulo=meta.get("titulo", t["titulo"]))
        db.actualizar(tid, estado="aprobado", etapa="aprobado por una persona")
        db.registrar("Panel", "Aprobado por una persona", tid)
        if accion == "publicar":
            res = publicador.publicar(db.obtener(tid))
            return jsonify({"ok": True, "publicacion": res})
    elif accion == "guardar":
        meta = {**t["datos"].get("metadatos", {}), **(b.get("metadatos") or {})}
        db.fusionar_datos(tid, metadatos=meta)
        db.actualizar(tid, titulo=meta.get("titulo", t["titulo"]))
    elif accion == "rechazar":
        db.actualizar(tid, estado="rechazado", etapa=b.get("motivo", "rechazado"))
        db.registrar("Panel", f"Rechazado: {b.get('motivo', 'sin motivo')}", tid, "aviso")
    elif accion == "regenerar":
        if b.get("instrucciones"):
            db.fusionar_datos(tid, instrucciones=b["instrucciones"])
        db.actualizar(tid, estado="en_cola", etapa="regenerar", progreso=0, error="")
        db.registrar("Panel", "Vuelve a la cola para regenerar", tid)
    elif accion == "permiso":
        db.fusionar_datos(tid, permiso_manual=True)
        db.registrar("Panel", "Permiso del creador confirmado a mano", tid)
    elif accion == "borrar":
        db.actualizar(tid, estado="descartado")
    else:
        abort(400)
    return jsonify({"ok": True})


@app.route("/api/trabajador", methods=["POST"])
def api_trabajador():
    if (request.json or {}).get("encender"):
        orquestador.encender()
    else:
        orquestador.apagar()
    return jsonify({"trabajador": orquestador.encendido()})


@app.route("/api/ciclo", methods=["POST"])
def api_ciclo():
    orquestador.forzar_ciclo()
    return jsonify({"ok": True})


@app.route("/api/ajustes", methods=["GET", "POST"])
def api_ajustes():
    if request.method == "POST":
        return jsonify(guardar_ajustes(request.json or {}))
    return jsonify(cargar_ajustes())


@app.route("/api/claves", methods=["GET", "POST"])
def api_claves():
    env = BASE_DIR / ".env"
    if request.method == "POST":
        nuevas = {k: v.strip() for k, v in (request.json or {}).items() if k in CLAVES and v and "•" not in v}
        lineas = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
        hechas = set()
        for i, l in enumerate(lineas):
            k = l.split("=", 1)[0].strip()
            if k in nuevas:
                lineas[i] = f"{k}={nuevas[k]}"
                hechas.add(k)
        lineas += [f"{k}={v}" for k, v in nuevas.items() if k not in hechas]
        env.write_text("\n".join(lineas) + "\n", encoding="utf-8")
        os.environ.update(nuevas)
    return jsonify({k: ("••••" + os.environ[k][-4:]) if os.environ.get(k) else "" for k in CLAVES})


@app.route("/api/canales")
def api_canales():
    return jsonify(canales.listar())


@app.route("/api/llm/probar")
def api_probar_llm():
    return jsonify(llm.probar_proveedores())


@app.route("/api/nichos", methods=["GET", "POST"])
def api_nichos():
    if request.method == "POST":
        guardar_nichos(request.json or [])
    nichos = cargar_nichos()
    for n in nichos:
        perfil = cargar_estilo(n["id"])
        n["_estilo"] = {k: perfil.get(k) for k in ("tono", "ganchos", "estructura", "formulas_titulo", "cierre",
                                                    "actualizado", "motor", "estadisticas_titulos")} if perfil else None
        n["_edicion"] = perfil.get("edicion") if perfil else None
    return jsonify(nichos)


@app.route("/api/nichos/<nid>/analizar", methods=["POST"])
def api_analizar(nid):
    def tarea():
        try:
            analista.analizar_nicho(nid)
        except Exception as e:
            from fabrica.agentes import fallo
            fallo("analista", str(e))
    threading.Thread(target=tarea, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/nichos/<nid>/edicion", methods=["POST"])
def api_analizar_edicion(nid):
    def tarea():
        try:
            analista.analizar_edicion(nid)
        except Exception as e:
            from fabrica.agentes import fallo
            fallo("analista", str(e))
    threading.Thread(target=tarea, daemon=True).start()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Biblioteca de recursos
# ---------------------------------------------------------------------------

@app.route("/api/biblioteca")
def api_biblioteca():
    tipo = request.args.get("tipo") or None
    q = request.args.get("q", "").strip()
    return jsonify({"recursos": biblioteca.listar(tipo, q, limite=300), "estadisticas": biblioteca.estadisticas()})


@app.route("/api/biblioteca", methods=["POST"])
def api_biblioteca_subir():
    from werkzeug.utils import secure_filename
    f = request.files.get("archivo")
    if not f or not f.filename:
        return jsonify({"error": "Falta el archivo"}), 400
    licencia = biblioteca.normalizar_licencia(request.form.get("licencia", ""))
    if not licencia:
        return jsonify({"error": "Esa licencia no permite uso comercial o modificaciones. Solo CC0, dominio público, "
                                 "CC BY, CC BY-SA, Pexels, Pixabay, NASA o material propio."}), 400
    ext = Path(f.filename).suffix.lower()
    tipo = {".mp4": "video", ".mov": "video", ".webm": "video", ".jpg": "imagen", ".jpeg": "imagen", ".png": "imagen",
            ".webp": "imagen", ".mp3": "audio", ".wav": "audio", ".ogg": "audio"}.get(ext)
    if not tipo:
        return jsonify({"error": "Formato no admitido"}), 400
    destino = biblioteca.BIBLIOTECA_DIR / "propios"
    destino.mkdir(parents=True, exist_ok=True)
    ruta = destino / f"{int(time.time())}_{secure_filename(f.filename) or 'archivo' + ext}"
    f.save(ruta)
    rid = biblioteca.agregar(str(ruta), tipo, licencia, credito=request.form.get("credito", ""), origen="propio",
                             url_origen=request.form.get("url_origen", ""), etiquetas=request.form.get("etiquetas", ""),
                             descripcion=request.form.get("descripcion", ""), nicho=request.form.get("nicho", ""),
                             subtipo=request.form.get("subtipo", ""), copiar=False)
    return jsonify({"ok": True, "id": rid})


@app.route("/api/biblioteca/<int:rid>", methods=["DELETE"])
def api_biblioteca_borrar(rid):
    biblioteca.borrar(rid, borrar_archivo=True)
    return jsonify({"ok": True})


@app.route("/api/biblioteca/importar", methods=["POST"])
def api_biblioteca_importar():
    b = request.json or {}
    carpeta = (BASE_DIR / b.get("carpeta", "assets/biblioteca/propios")).resolve()
    if BASE_DIR.resolve() not in carpeta.parents and carpeta != BASE_DIR.resolve() or not carpeta.is_dir():
        return jsonify({"error": "La carpeta tiene que estar dentro del proyecto y existir"}), 400
    if not biblioteca.normalizar_licencia(b.get("licencia", "")):
        return jsonify({"error": "Licencia no válida para uso comercial"}), 400
    n = biblioteca.importar_carpeta(carpeta, b["licencia"], b.get("credito", ""), b.get("nicho", ""))
    return jsonify({"ok": True, "importados": n})


@app.route("/api/biblioteca/embeddings", methods=["POST"])
def api_biblioteca_embeddings():
    threading.Thread(target=biblioteca.recalcular_embeddings, daemon=True).start()
    return jsonify({"ok": True, "estado": biblioteca.estado_semantico()})


@app.route("/media/biblioteca/<int:rid>")
def media_biblioteca(rid):
    r = biblioteca.obtener(rid)
    if not r or not Path(r["ruta"]).exists():
        abort(404)
    p = Path(r["ruta"]).resolve()
    if BASE_DIR.resolve() not in p.parents:
        abort(403)
    return send_from_directory(p.parent, p.name)


@app.route("/api/fuentes", methods=["GET", "POST"])
def api_fuentes():
    if request.method == "POST":
        guardar_fuentes(request.json or [])
    return jsonify(cargar_fuentes())


@app.route("/api/laboratorio", methods=["POST"])
def api_laboratorio():
    texto = (request.json or {}).get("texto", "")
    if not texto.strip():
        return jsonify({"error": "Pega un texto"}), 400
    if (request.json or {}).get("solo_medir"):
        return jsonify({"antes": estilo.puntaje_humano(texto)})
    return jsonify(estilo.humanizar(texto))


# ---------------------------------------------------------------------------
# Whop: campañas de clipping pagadas por vistas
# ---------------------------------------------------------------------------

def _campana_o_404(cid):
    c = whop.obtener_campana(cid)
    if not c:
        abort(404)
    return c


@app.route("/api/whop/campanas")
def api_whop_campanas():
    return jsonify({"campanas": whop.listar_campanas(), "plataformas": whop.PLATAFORMAS})


@app.route("/api/whop/campanas", methods=["POST"])
def api_whop_crear():
    b = request.json or {}
    if not (b.get("nombre") or "").strip():
        return jsonify({"error": "Ponle nombre a la campaña"}), 400
    cid = whop.crear_campana(b["nombre"], b)
    lanzados = whop.lanzar_material(cid) if b.get("lanzar") else []
    return jsonify({"id": cid, "lanzados": lanzados})


@app.route("/api/whop/campanas/<int:cid>")
def api_whop_campana(cid):
    c = _campana_o_404(cid)
    trabajos = db.listar(limite=5000)
    envs = whop.listar_envios(cid)
    clips = []
    for t in whop.trabajos_de(cid, trabajos):
        r = _resumen(t)
        meta = t["datos"].get("metadatos", {})
        r.update({"fuente_url": t["fuente_url"], "video_url": f"/media/trabajo/{t['id']}/final.mp4" if t["datos"].get("video") else "",
                  "metadatos": {k: meta.get(k) for k in ("titulo", "descripcion", "tags", "captions")},
                  "inicio": t["datos"].get("inicio"), "fin": t["datos"].get("fin"),
                  "enlaces": [e for e in envs if e["trabajo_id"] == t["id"]],
                  "por_subir": t["tipo"] == "clip" and whop.pendiente_de_subir(t, c, envs)})
        clips.append(r)
    for e in envs:
        e["estimado"] = whop.ganancia(e["vistas"], c)
    return jsonify({**c, "resumen": whop.resumen(c, trabajos, envs), "clips": clips, "envios": envs})


@app.route("/api/whop/campanas/<int:cid>", methods=["POST"])
def api_whop_editar(cid):
    _campana_o_404(cid)
    b = request.json or {}
    whop.actualizar_campana(cid, nombre=b.get("nombre"), estado=b.get("estado"),
                            datos={k: v for k, v in b.items() if k in whop.CAMPANA_DEFECTO} or None)
    return jsonify({"ok": True})


@app.route("/api/whop/campanas/<int:cid>", methods=["DELETE"])
def api_whop_cerrar(cid):
    _campana_o_404(cid)
    whop.borrar_campana(cid)
    return jsonify({"ok": True})


@app.route("/api/whop/campanas/<int:cid>/material", methods=["POST"])
def api_whop_material(cid):
    _campana_o_404(cid)
    try:
        ids = whop.lanzar_material(cid, (request.json or {}).get("urls"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True, "lanzados": ids})


@app.route("/api/whop/reglas", methods=["POST"])
def api_whop_reglas():
    texto = (request.json or {}).get("texto", "")
    if not texto.strip():
        return jsonify({"error": "Pega el texto de la campaña"}), 400
    return jsonify(whop.extraer_reglas(texto))


@app.route("/api/whop/envios", methods=["POST"])
def api_whop_envio():
    b = request.json or {}
    try:
        eid = whop.registrar_envio(int(b.get("campana_id") or 0), b.get("url", ""),
                                   int(b["trabajo_id"]) if b.get("trabajo_id") else None, b.get("plataforma", ""))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"id": eid})


@app.route("/api/whop/envios/<int:eid>", methods=["POST", "DELETE"])
def api_whop_envio_editar(eid):
    if not whop.obtener_envio(eid):
        abort(404)
    if request.method == "DELETE":
        whop.borrar_envio(eid)
    else:
        b = request.json or {}
        campos = {k: b[k] for k in ("estado", "notas") if k in b}
        for k, conv in (("vistas", int), ("pago", float)):
            if k in b:
                try:
                    campos[k] = conv(b[k] or 0)
                except (TypeError, ValueError):
                    return jsonify({"error": f"{k} no es un número"}), 400
        whop.actualizar_envio(eid, **campos)
    return jsonify({"ok": True})


@app.route("/api/whop/envios/<int:eid>/vistas", methods=["POST"])
def api_whop_vistas(eid):
    try:
        return jsonify({"vistas": whop.leer_vistas(eid)})
    except Exception as e:
        return jsonify({"error": f"No pude leer las vistas: {str(e)[:200]}. Ponlas a mano."}), 400


@app.route("/api/whop/vistas", methods=["POST"])
def api_whop_todas_vistas():
    threading.Thread(target=whop.actualizar_todas_las_vistas, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/whop/clips/<int:tid>/youtube", methods=["POST"])
def api_whop_youtube(tid):
    t = db.obtener(tid)
    if not t or not t["datos"].get("campana_id"):
        abort(404)
    if t["estado"] not in ("aprobado", "programado"):
        return jsonify({"error": "Primero apruébalo en Revisión"}), 400
    return jsonify(publicador.publicar(t))


def run_server(host="127.0.0.1", port=5050, trabajador=True):
    if trabajador:
        orquestador.encender()
    print("=" * 64)
    print("  FÁBRICA DE CONTENIDO · Sala de control")
    print(f"  Abre en tu navegador: http://{host}:{port}")
    print("=" * 64)
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    run_server()
