"""
Fábrica de Contenido: punto de entrada.

  python fabrica.py panel              Abre la sala de control (y enciende el trabajador)
  python fabrica.py trabajador         Solo el trabajador, sin interfaz (para una VPS)
  python fabrica.py ciclo              Una pasada del Explorador + procesa la cola y termina (para cron)
  python fabrica.py clip URL --nicho clips_streams [--permiso]
  python fabrica.py original "tema" --nicho curiosidades [--url REFERENCIA] [--formato largo]
  python fabrica.py estilo NICHO       El Analista estudia los canales de referencia del nicho
  python fabrica.py edicion NICHO      El Analista mide cortes e insertos de los canales de referencia
  python fabrica.py biblioteca importar CARPETA --licencia cc0 [--credito AUTOR] [--nicho N]
  python fabrica.py biblioteca indice  Calcula la búsqueda por significado (requiere sentence-transformers)
  python fabrica.py biblioteca buscar "texto"
  python fabrica.py estado             Resumen de la cola
  python fabrica.py conectar-canal ALIAS   Autoriza un canal de YouTube (por SSH con túnel en el puerto 8765)
  python fabrica.py canales            Lista los canales conectados
"""
import sys
import time
import argparse
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

from fabrica import db, orquestador
from fabrica.agentes import explorador, analista


def vaciar_cola() -> None:
    while True:
        t = db.tomar_siguiente()
        if not t:
            break
        orquestador.procesar(t)
    from fabrica.agentes import publicador
    publicador.programar_aprobados()
    publicador.publicar_pendientes()


def main():
    p = argparse.ArgumentParser(description="Fábrica de Contenido multi-nicho")
    sub = p.add_subparsers(dest="cmd")
    pa = sub.add_parser("panel")
    pa.add_argument("--puerto", type=int, default=5050)
    pa.add_argument("--host", default="127.0.0.1", help="0.0.0.0 para verlo desde otra máquina (VPS)")
    pa.add_argument("--sin-trabajador", action="store_true")
    sub.add_parser("trabajador")
    sub.add_parser("ciclo")
    pc = sub.add_parser("clip")
    pc.add_argument("url")
    pc.add_argument("--nicho", default="clips_streams")
    pc.add_argument("--formato", default="short", choices=["short", "largo"])
    pc.add_argument("--permiso", action="store_true", help="Confirmas que el creador permite clips")
    po = sub.add_parser("original")
    po.add_argument("tema", nargs="?", default="")
    po.add_argument("--url", default="")
    po.add_argument("--nicho", default="curiosidades")
    po.add_argument("--formato", default="short", choices=["short", "largo"])
    po.add_argument("--instrucciones", default="")
    pe = sub.add_parser("estilo")
    pe.add_argument("nicho")
    ped = sub.add_parser("edicion")
    ped.add_argument("nicho")
    pb = sub.add_parser("biblioteca")
    pb.add_argument("accion", choices=["importar", "indice", "buscar", "resumen"])
    pb.add_argument("valor", nargs="?", default="")
    pb.add_argument("--licencia", default="propio")
    pb.add_argument("--credito", default="")
    pb.add_argument("--nicho", default="")
    sub.add_parser("estado")
    pcc = sub.add_parser("conectar-canal")
    pcc.add_argument("alias", help="Nombre corto del canal, p. ej. curiosidades")
    pcc.add_argument("--puerto", type=int, default=8765)
    sub.add_parser("canales")
    a = p.parse_args()

    db.iniciar()
    if a.cmd in (None, "panel"):
        from fabrica_app import run_server
        run_server(host=getattr(a, "host", "127.0.0.1"), port=getattr(a, "puerto", 5050),
                   trabajador=not getattr(a, "sin_trabajador", False))
    elif a.cmd == "trabajador":
        orquestador.encender()
        print("Trabajador encendido. Ctrl+C para parar.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            orquestador.apagar()
    elif a.cmd == "ciclo":
        explorador.ciclo()
        vaciar_cola()
    elif a.cmd == "clip":
        tid = db.crear_trabajo("fuente_clip", a.nicho, a.formato, fuente_url=a.url, titulo=a.url,
                               datos={"permiso_manual": a.permiso, "origen": "cli"})
        print(f"Trabajo #{tid} creado")
        vaciar_cola()
    elif a.cmd == "original":
        tid = db.crear_trabajo("original", a.nicho, a.formato, fuente_url=a.url, titulo=a.tema or a.url,
                               datos={"tema": a.tema, "instrucciones": a.instrucciones, "origen": "cli"})
        print(f"Trabajo #{tid} creado")
        vaciar_cola()
    elif a.cmd == "estilo":
        perfil = analista.analizar_nicho(a.nicho)
        print(perfil)
    elif a.cmd == "edicion":
        import json
        print(json.dumps(analista.analizar_edicion(a.nicho), ensure_ascii=False, indent=2))
    elif a.cmd == "biblioteca":
        from fabrica import biblioteca
        if a.accion == "importar":
            if not biblioteca.normalizar_licencia(a.licencia):
                sys.exit(f"La licencia «{a.licencia}» no permite uso comercial o modificaciones.")
            print(f"Importados: {biblioteca.importar_carpeta(Path(a.valor), a.licencia, a.credito, a.nicho)}")
        elif a.accion == "indice":
            print(f"Recursos indexados: {biblioteca.recalcular_embeddings()} ({biblioteca.estado_semantico()})")
        elif a.accion == "buscar":
            for r in biblioteca.buscar(a.valor, ("video", "imagen", "audio"), n=10):
                print(f"{r['puntaje']:5}  #{r['id']:<5} {r['tipo']:7} {r['licencia']:9} {r['etiquetas'][:60]}")
        else:
            print(biblioteca.estadisticas())
    elif a.cmd == "conectar-canal":
        from fabrica import canales
        info = canales.conectar(a.alias, a.puerto)
        print(f"Canal conectado: {info}")
        print(f"Pon «{info['alias']}» en el campo 'Canal de YouTube' de los nichos que deban publicar ahí.")
    elif a.cmd == "canales":
        from fabrica import canales
        for c in canales.listar():
            print(f"{c['alias']:20} {c['titulo']:40} {c['id']}")
    elif a.cmd == "estado":
        for k, v in db.contar_por_estado().items():
            print(f"{k:12} {v}")


if __name__ == "__main__":
    main()
