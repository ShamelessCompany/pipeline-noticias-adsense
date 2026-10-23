"""
Módulo de captura limpia de capturas (Playwright) en Modo Oscuro.
Permite capturar noticias o tweets desde una URL real o renderizar una tarjeta
editorial local de alta fidelidad sin bloqueos de login.
"""
import os
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright

def generate_mock_tweet_html(
    author_name: str,
    author_handle: str,
    author_avatar: str,
    content: str,
    timestamp: str = "Hoy · 11:30 AM",
    metrics: dict = None
) -> str:
    """Genera HTML limpio con estilo Twitter / X en Modo Oscuro a 1080px de ancho."""
    if metrics is None:
        metrics = {"replies": "1.2K", "reposts": "4.8K", "likes": "35K", "views": "1.2M"}
        
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: transparent;
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 100vh;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      padding: 40px;
    }}
    .tweet-card {{
      width: 960px;
      background: #000000;
      border: 1px solid #2f3336;
      border-radius: 24px;
      padding: 36px 42px;
      color: #e7e9ea;
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.7);
    }}
    .tweet-header {{
      display: flex;
      align-items: center;
      margin-bottom: 24px;
    }}
    .avatar {{
      width: 80px;
      height: 80px;
      border-radius: 50%;
      background: linear-gradient(135deg, #1d9bf0, #7928ca);
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 700;
      font-size: 32px;
      color: #ffffff;
      margin-right: 20px;
      flex-shrink: 0;
    }}
    .user-info {{
      display: flex;
      flex-direction: column;
    }}
    .name-row {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .name {{
      font-weight: 800;
      font-size: 32px;
      color: #f7f9f9;
    }}
    .badge {{
      display: inline-block;
      width: 26px;
      height: 26px;
      background: #1d9bf0;
      border-radius: 50%;
      position: relative;
    }}
    .badge::after {{
      content: '✓';
      position: absolute;
      color: white;
      font-size: 18px;
      left: 6px;
      top: 1px;
    }}
    .handle {{
      color: #71767b;
      font-size: 24px;
      margin-top: 4px;
    }}
    .tweet-content {{
      font-size: 36px;
      line-height: 1.45;
      color: #e7e9ea;
      word-break: break-word;
      margin-bottom: 24px;
    }}
    .tweet-content .highlight {{
      background: rgba(254, 218, 54, 0.25);
      border-left: 6px solid #feda36;
      padding: 4px 12px;
      border-radius: 6px;
      display: block;
      margin: 16px 0;
      color: #ffffff;
      font-weight: 600;
    }}
    .tweet-meta {{
      color: #71767b;
      font-size: 22px;
      padding-bottom: 20px;
      border-bottom: 1px solid #2f3336;
      margin-bottom: 20px;
    }}
    .tweet-metrics {{
      display: flex;
      justify-content: space-between;
      color: #71767b;
      font-size: 24px;
      padding: 6px 12px;
    }}
    .metric span {{
      color: #e7e9ea;
      font-weight: 700;
    }}
  </style>
</head>
<body>
  <div class="tweet-card" id="capture-target">
    <div class="tweet-header">
      <div class="avatar">{author_avatar or author_name[:2].upper()}</div>
      <div class="user-info">
        <div class="name-row">
          <span class="name">{author_name}</span>
          <span class="badge"></span>
        </div>
        <span class="handle">{author_handle}</span>
      </div>
    </div>
    <div class="tweet-content">
      {content}
    </div>
    <div class="tweet-meta">
      {timestamp} · Difusión Oficial
    </div>
    <div class="tweet-metrics">
      <div class="metric"><span>{metrics['replies']}</span> Respuestas</div>
      <div class="metric"><span>{metrics['reposts']}</span> Reposts</div>
      <div class="metric"><span>{metrics['likes']}</span> Me gusta</div>
      <div class="metric"><span>{metrics['views']}</span> Vistas</div>
    </div>
  </div>
</body>
</html>"""

def capture_screenshot(
    output_image_path: str,
    url: str = None,
    html_content: str = None,
    viewport_width: int = 1080,
    viewport_height: int = 1920
) -> str:
    """
    Captura una captura de pantalla limpia en modo oscuro utilizando Playwright.
    Soporta URLs reales o plantillas HTML enriquecidas locales.
    """
    output_path = Path(output_image_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": viewport_width, "height": viewport_height},
            color_scheme="dark",
            device_scale_factor=2
        )
        page = context.new_page()

        if html_content:
            page.set_content(html_content, wait_until="networkidle")
            # Recortar directo al elemento de la tarjeta
            card = page.locator("#capture-target")
            if card.count() > 0:
                card.screenshot(path=str(output_path), omit_background=True)
            else:
                page.screenshot(path=str(output_path), full_page=True)
        elif url:
            page.goto(url, wait_until="networkidle")
            # Inyectar CSS para ocultar cookies y banners comunes
            page.add_style_tag(content="""
                #cookie-banner, .cookie-banner, [aria-label*="cookie"],
                [class*="cookie"], [id*="cookie"], .modal, .popup {
                    display: none !important;
                }
            """)
            page.screenshot(path=str(output_path), full_page=False)
        else:
            raise ValueError("Se debe proporcionar 'url' o 'html_content'")

        browser.close()

    return str(output_path)
