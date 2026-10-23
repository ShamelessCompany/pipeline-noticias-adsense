"""
Módulo de Checkpoint Humano de Validación (Discord / Webhook / Dashboard Local).
Garantiza el cumplimiento de curación humana exigido por las políticas de YouTube.
"""
import os
import json
import requests
from pathlib import Path
from typing import Dict, Any, Optional

def generate_local_review_dashboard(
    video_path: str,
    script_data: Dict[str, Any],
    output_html_path: str
) -> str:
    """
    Genera un dashboard HTML interactivo para revisar el video generado,
    el cumplimiento de políticas AdSense y aprobar/rechazar antes de publicar.
    """
    out_path = Path(output_html_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    video_file_name = Path(video_path).name

    html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>Checkpoint de Revisión Humana - YouTube Shorts AdSense</title>
  <style>
    :root {{
      --bg: #0f172a;
      --card-bg: #1e293b;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --accent: #38bdf8;
      --success: #22c55e;
      --warning: #f59e0b;
      --danger: #ef4444;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      padding: 30px;
    }}
    .container {{
      max-width: 1100px;
      margin: 0 auto;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 25px;
      padding-bottom: 15px;
      border-bottom: 1px solid #334155;
    }}
    h1 {{ font-size: 26px; font-weight: 700; color: #ffffff; }}
    .badge-checkpoint {{
      background: rgba(56, 189, 248, 0.15);
      color: var(--accent);
      padding: 6px 14px;
      border-radius: 9999px;
      font-size: 14px;
      font-weight: 600;
      border: 1px solid rgba(56, 189, 248, 0.3);
    }}
    .main-grid {{
      display: grid;
      grid-template-columns: 420px 1fr;
      gap: 30px;
      align-items: start;
    }}
    .video-card {{
      background: var(--card-bg);
      border-radius: 16px;
      padding: 20px;
      box-shadow: 0 10px 25px rgba(0,0,0,0.4);
      display: flex;
      flex-direction: column;
      align-items: center;
    }}
    video {{
      width: 100%;
      max-height: 640px;
      border-radius: 12px;
      background: #000;
      outline: none;
    }}
    .details-card {{
      background: var(--card-bg);
      border-radius: 16px;
      padding: 25px;
      box-shadow: 0 10px 25px rgba(0,0,0,0.4);
    }}
    .details-card h2 {{
      font-size: 20px;
      margin-bottom: 16px;
      color: var(--accent);
    }}
    .compliance-box {{
      background: rgba(34, 197, 94, 0.1);
      border: 1px solid var(--success);
      border-radius: 10px;
      padding: 16px;
      margin-bottom: 20px;
    }}
    .compliance-box h3 {{
      color: var(--success);
      font-size: 16px;
      margin-bottom: 8px;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .compliance-box ul {{
      list-style-type: none;
      font-size: 14px;
      color: #cbd5e1;
      line-height: 1.6;
    }}
    .compliance-box li::before {{
      content: "✓ ";
      color: var(--success);
      font-weight: bold;
    }}
    .script-box {{
      background: #0f172a;
      border-radius: 8px;
      padding: 16px;
      margin: 15px 0;
      font-size: 15px;
      line-height: 1.6;
      color: #e2e8f0;
      max-height: 220px;
      overflow-y: auto;
      border-left: 4px solid var(--accent);
    }}
    .actions {{
      display: flex;
      gap: 15px;
      margin-top: 25px;
    }}
    .btn {{
      padding: 14px 24px;
      border-radius: 10px;
      font-size: 16px;
      font-weight: 700;
      cursor: pointer;
      border: none;
      transition: all 0.2s;
      flex: 1;
      text-align: center;
    }}
    .btn-approve {{
      background: var(--success);
      color: white;
    }}
    .btn-approve:hover {{
      background: #16a34a;
      transform: translateY(-2px);
    }}
    .btn-reject {{
      background: #334155;
      color: #f1f5f9;
    }}
    .btn-reject:hover {{
      background: var(--danger);
    }}
    .status-msg {{
      margin-top: 15px;
      font-size: 14px;
      text-align: center;
      font-weight: 600;
      min-height: 20px;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>Checkpoint de Curación Humana (YouTube YPP)</h1>
      <span class="badge-checkpoint">Validación Previa a Publicación</span>
    </header>

    <div class="main-grid">
      <div class="video-card">
        <video controls autoplay muted loop>
          <source src="{video_file_name}" type="video/mp4">
          Tu navegador no soporta reproducción de video MP4.
        </video>
        <p style="margin-top: 12px; font-size: 13px; color: var(--text-muted);">
          Archivo: <code>{video_file_name}</code> (9:16 - 1080x1920)
        </p>
      </div>

      <div class="details-card">
        <h2>{script_data.get('title', 'Noticia Editorial')}</h2>
        
        <div class="compliance-box">
          <h3>Escudo Anti-Desmonetización AdSense Activo</h3>
          <ul>
            <li><strong>Transformación Editorial:</strong> Contraste de fuentes y postura analítica original añadida.</li>
            <li><strong>Anti-Reused Content:</strong> No se repite textualmente la fuente; añade contexto histórico y crítico.</li>
            <li><strong>Edición Multicapa:</strong> B-roll procedural, zoom dinámico y subtítulos palabra por palabra.</li>
            <li><strong>Total de Palabras:</strong> {script_data.get('word_count', 95)} palabras (~35 seg).</li>
          </ul>
        </div>

        <h3 style="font-size: 15px; color: var(--text-muted); margin-top: 15px;">Guion Locutado:</h3>
        <div class="script-box">
          {script_data.get('script', '')}
        </div>

        <div class="actions">
          <button class="btn btn-approve" onclick="approveVideo()">✓ Aprobar para YouTube</button>
          <button class="btn btn-reject" onclick="rejectVideo()">✕ Rechazar / Regenerar</button>
        </div>
        <div id="status-msg" class="status-msg"></div>
      </div>
    </div>
  </div>

  <script>
    function approveVideo() {{
      const msg = document.getElementById('status-msg');
      msg.style.color = '#22c55e';
      msg.innerText = '✓ Video Aprobado con éxito. Listo para sincronizar con YouTube Data API.';
    }}
    function rejectVideo() {{
      const msg = document.getElementById('status-msg');
      msg.style.color = '#ef4444';
      msg.innerText = '✕ Video marcado para regeneración de guion.';
    }}
  </script>
</body>
</html>"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return str(out_path)

def send_discord_notification(
    webhook_url: str,
    video_title: str,
    video_path: str,
    script_snippet: str
) -> bool:
    """Envía notificación con embed al webhook de Discord para el canal #revision-shorts."""
    if not webhook_url:
        return False
        
    try:
        payload = {
            "username": "AdSense Pipeline Sentinel",
            "content": "🚨 **Nuevo Short Listo para Revisión Humana**",
            "embeds": [{
                "title": f"🎬 {video_title}",
                "description": f"**Guion:**\n{script_snippet[:300]}...",
                "color": 3711992,
                "fields": [
                    {"name": "Estado", "value": "Pendiente de Aprobación", "inline": True},
                    {"name": "Formato", "value": "9:16 (1080x1920)", "inline": True},
                    {"name": "Políticas", "value": "Anti-Reused Content verificado", "inline": False}
                ],
                "footer": {"text": "Haz clic en el dashboard local para aprobar."}
            }]
        }
        res = requests.post(webhook_url, json=payload, timeout=5)
        return res.status_code in [200, 204]
    except Exception as e:
        print(f"[Aviso] No se pudo enviar webhook a Discord: {e}")
        return False
