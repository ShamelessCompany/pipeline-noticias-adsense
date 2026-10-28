"""
Canales de YouTube conectados. Cada canal tiene un alias (por ejemplo "curiosidades")
y su propio token OAuth en data/canales/<alias>.json; cada nicho elige en qué canal publica.

Conectar un canal en una VPS sin navegador:
  1. Desde tu PC abre un túnel:  ssh -L 8765:localhost:8765 usuario@IP_DE_LA_VPS
  2. En la VPS:                  python fabrica.py conectar-canal ALIAS
  3. Abre en tu navegador el enlace que imprime, entra con la cuenta de Google y elige el canal.
     Google redirige a localhost:8765, que el túnel lleva de vuelta a la VPS.
"""
import json
import re
from typing import Dict, List, Optional

from fabrica.ajustes import BASE_DIR, DATA_DIR

CANALES_DIR = DATA_DIR / "canales"
CANALES_DIR.mkdir(parents=True, exist_ok=True)
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]
PUERTO_OAUTH = 8765


def _alias_valido(alias: str) -> str:
    alias = (alias or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9_-]{1,40}", alias):
        raise ValueError("El alias solo puede tener letras minúsculas, números, - y _")
    return alias


def _ruta_token(alias: str):
    return CANALES_DIR / f"{alias}.json"


def _ruta_info(alias: str):
    return CANALES_DIR / f"{alias}.info.json"


def conectar(alias: str, puerto: int = PUERTO_OAUTH) -> Dict:
    """Autoriza un canal con OAuth y guarda su token. Pensado para correr por SSH con túnel."""
    alias = _alias_valido(alias)
    secretos = BASE_DIR / "client_secrets.json"
    if not secretos.exists():
        raise RuntimeError("Falta client_secrets.json en la carpeta del proyecto (OAuth de escritorio de Google Cloud)")
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(str(secretos), SCOPES)
    cred = flow.run_local_server(
        host="localhost", port=puerto, open_browser=False, access_type="offline", prompt="consent",
        authorization_prompt_message=(
            "\nAbre este enlace en el navegador de tu PC (con el túnel SSH en el puerto "
            f"{puerto} abierto) y elige el canal que quieres conectar:\n\n{{url}}\n"),
        success_message="Canal conectado. Ya puedes cerrar esta pestaña.")
    _ruta_token(alias).write_text(cred.to_json(), encoding="utf-8")
    info = {"alias": alias}
    try:
        from googleapiclient.discovery import build
        yt = build("youtube", "v3", credentials=cred, cache_discovery=False)
        items = yt.channels().list(part="snippet", mine=True).execute().get("items", [])
        if items:
            info.update(id=items[0]["id"], titulo=items[0]["snippet"]["title"])
    except Exception as e:
        info["aviso"] = f"Token guardado, pero no pude leer el nombre del canal: {e}"
    _ruta_info(alias).write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    return info


def credenciales(alias: str):
    """Devuelve credenciales válidas del canal, renovando el token si caducó."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    ruta = _ruta_token(_alias_valido(alias))
    if not ruta.exists():
        legado = DATA_DIR / "youtube_token.json"
        if alias == "principal" and legado.exists():
            ruta = legado
        else:
            raise RuntimeError(f"El canal «{alias}» no está conectado. En la VPS: python fabrica.py conectar-canal {alias}")
    cred = Credentials.from_authorized_user_file(str(ruta), SCOPES)
    if not cred.valid:
        if cred.expired and cred.refresh_token:
            cred.refresh(Request())
            ruta.write_text(cred.to_json(), encoding="utf-8")
        else:
            raise RuntimeError(f"El token del canal «{alias}» no sirve. Vuelve a conectarlo.")
    return cred


def listar() -> List[Dict]:
    out = []
    for p in sorted(CANALES_DIR.glob("*.json")):
        if p.name.endswith(".info.json"):
            continue
        alias = p.stem
        info: Optional[Dict] = None
        if _ruta_info(alias).exists():
            try:
                info = json.loads(_ruta_info(alias).read_text(encoding="utf-8"))
            except Exception:
                info = None
        out.append({"alias": alias, "titulo": (info or {}).get("titulo", ""), "id": (info or {}).get("id", "")})
    return out


def desconectar(alias: str) -> None:
    for p in (_ruta_token(_alias_valido(alias)), _ruta_info(alias)):
        if p.exists():
            p.unlink()
