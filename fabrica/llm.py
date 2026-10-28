"""
Router de modelos de lenguaje con costo cero.

Prueba los proveedores en el orden de data/ajustes.json y usa el primero que responda:
- gemini:   API de Google AI Studio (capa gratuita). Clave en GEMINI_API_KEY.
- opencode: modelos gratuitos de OpenCode Zen (API compatible con OpenAI). Clave en OPENCODE_API_KEY.
- ollama:   modelo local en tu máquina (http://localhost:11434), sin clave.
- local:    sin modelo; las funciones que llaman al router usan su respaldo heurístico.

Si ningún proveedor responde, generar() devuelve None y cada agente sigue con su plan B.
"""
import os
import re
import json
import time
from typing import Optional, Any, Dict, List

import requests

from fabrica.ajustes import cargar_ajustes

_ultimo_proveedor = {"nombre": "local", "error": ""}


def proveedor_activo() -> Dict[str, str]:
    return dict(_ultimo_proveedor)


def _gemini(prompt: str, sistema: str, cfg: dict, temperatura: float, json_mode: bool) -> Optional[str]:
    key = os.getenv(cfg.get("api_key_env", "GEMINI_API_KEY"), "")
    if not key:
        return None
    modelo = cfg.get("modelo") or "gemini-2.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
    body: Dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperatura},
    }
    if sistema:
        body["systemInstruction"] = {"parts": [{"text": sistema}]}
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"
    r = requests.post(url, params={"key": key}, json=body, timeout=120)
    r.raise_for_status()
    partes = r.json()["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in partes).strip()


def _openai_compatible(prompt: str, sistema: str, cfg: dict, temperatura: float,
                       json_mode: bool, requiere_clave: bool) -> Optional[str]:
    key = os.getenv(cfg.get("api_key_env", ""), "") if cfg.get("api_key_env") else ""
    if requiere_clave and not key:
        return None
    modelo = cfg.get("modelo")
    if not modelo:
        return None
    mensajes: List[dict] = []
    if sistema:
        mensajes.append({"role": "system", "content": sistema})
    mensajes.append({"role": "user", "content": prompt})
    body: Dict[str, Any] = {"model": modelo, "messages": mensajes, "temperature": temperatura}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    r = requests.post(cfg["base_url"].rstrip("/") + "/chat/completions", json=body, headers=headers, timeout=180)
    if r.status_code == 400 and json_mode:
        # Algunos modelos gratuitos no aceptan response_format; reintentar sin él
        body.pop("response_format", None)
        r = requests.post(cfg["base_url"].rstrip("/") + "/chat/completions", json=body, headers=headers, timeout=180)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def generar(prompt: str, sistema: str = "", json_mode: bool = False,
            temperatura: Optional[float] = None) -> Optional[str]:
    ajustes = cargar_ajustes()["llm"]
    temp = ajustes.get("temperatura", 0.8) if temperatura is None else temperatura
    for nombre in ajustes.get("orden", []):
        if nombre == "local":
            break
        cfg = ajustes.get(nombre, {})
        try:
            if nombre == "gemini":
                txt = _gemini(prompt, sistema, cfg, temp, json_mode)
            elif nombre == "opencode":
                txt = _openai_compatible(prompt, sistema, cfg, temp, json_mode, requiere_clave=True)
            elif nombre == "ollama":
                txt = _openai_compatible(prompt, sistema, cfg, temp, json_mode, requiere_clave=False)
            else:
                continue
            if txt:
                _ultimo_proveedor.update(nombre=f"{nombre}:{cfg.get('modelo', '')}", error="")
                return txt
        except Exception as e:
            _ultimo_proveedor.update(error=f"{nombre}: {e}"[:300])
            time.sleep(0.5)
    _ultimo_proveedor.update(nombre="local")
    return None


def ver_imagenes(prompt: str, imagenes: List[str], sistema: str = "") -> Optional[Any]:
    """
    Pregunta sobre unas imágenes (JPG) y devuelve JSON. Solo Gemini: es el proveedor gratuito con visión.
    Si no hay clave o falla, devuelve None y quien llama sigue sin esa información.
    """
    import base64
    cfg = cargar_ajustes()["llm"].get("gemini", {})
    key = os.getenv(cfg.get("api_key_env", "GEMINI_API_KEY"), "")
    if not key or not imagenes:
        return None
    partes: List[Dict[str, Any]] = [{"text": prompt}]
    for ruta in imagenes:
        with open(ruta, "rb") as f:
            partes.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(f.read()).decode()}})
    body: Dict[str, Any] = {"contents": [{"role": "user", "parts": partes}],
                            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}}
    if sistema:
        body["systemInstruction"] = {"parts": [{"text": sistema}]}
    modelo = cfg.get("modelo") or "gemini-2.5-flash"
    try:
        r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent",
                          params={"key": key}, json=body, timeout=180)
        r.raise_for_status()
        texto = "".join(p.get("text", "") for p in r.json()["candidates"][0]["content"]["parts"])
        return extraer_json(texto)
    except Exception as e:
        _ultimo_proveedor.update(error=f"gemini visión: {e}"[:300])
        return None


def extraer_json(texto: Optional[str]) -> Optional[Any]:
    """Saca el primer objeto o lista JSON de una respuesta, aunque venga con ```json o texto alrededor."""
    if not texto:
        return None
    limpio = re.sub(r"^```(?:json)?|```$", "", texto.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(limpio)
    except Exception:
        pass
    for abre, cierra in (("{", "}"), ("[", "]")):
        i, j = limpio.find(abre), limpio.rfind(cierra)
        if i != -1 and j > i:
            try:
                return json.loads(limpio[i:j + 1])
            except Exception:
                continue
    return None


def generar_json(prompt: str, sistema: str = "", temperatura: Optional[float] = None) -> Optional[Any]:
    return extraer_json(generar(prompt, sistema, json_mode=True, temperatura=temperatura))


def probar_proveedores() -> List[dict]:
    """Prueba cada proveedor por separado (lo usa el botón 'Probar' del panel)."""
    ajustes = cargar_ajustes()["llm"]
    resultados = []
    for nombre in ("gemini", "opencode", "ollama"):
        cfg = ajustes.get(nombre, {})
        inicio = time.time()
        try:
            if nombre == "gemini":
                txt = _gemini("Responde solo: ok", "", cfg, 0, False)
            else:
                txt = _openai_compatible("Responde solo: ok", "", cfg, 0, False, requiere_clave=(nombre == "opencode"))
            estado = "ok" if txt else "sin configurar"
            detalle = (txt or "Falta clave o modelo")[:80]
        except Exception as e:
            estado, detalle = "error", str(e)[:160]
        resultados.append({"proveedor": nombre, "modelo": cfg.get("modelo", ""), "estado": estado,
                           "detalle": detalle, "ms": int((time.time() - inicio) * 1000)})
    return resultados
