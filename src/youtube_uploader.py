"""
Módulo de Publicación en YouTube Data API v3 para YouTube Shorts.
Admite autenticación OAuth2 real y modo simulación/verificación pre-publicación.
"""
import os
import json
from pathlib import Path
from typing import Dict, Any, Optional

def upload_short_to_youtube(
    video_path: str,
    title: str,
    description: str,
    tags: Optional[list] = None,
    client_secrets_file: str = "client_secrets.json",
    privacy_status: str = "unlisted"
) -> Dict[str, Any]:
    """
    Sube un video a YouTube usando YouTube Data API v3.
    Si las credenciales no están presentes, opera en modo seguro simulado (Dry Run)
    mostrando los metadatos completos para verificación.
    """
    tags = tags or ["#shorts", "#noticias", "#actualidad", "#tecnologia"]
    if "#shorts" not in [t.lower() for t in tags] and "#shorts" not in title.lower():
        title = f"{title} #shorts"

    secrets_path = Path(client_secrets_file)
    if not secrets_path.exists():
        print("[YouTube Uploader] Modo Simulación: 'client_secrets.json' no encontrado.")
        print(f"[YouTube Uploader] Metadatos preparados para publicación:")
        print(f"  - Título: {title}")
        print(f"  - Categoría: 25 (News & Politics)")
        print(f"  - Privacidad: {privacy_status}")
        print(f"  - Tags: {', '.join(tags)}")
        return {
            "status": "simulated_success",
            "video_id": "simulated_id_shorts_demo",
            "title": title,
            "privacy": privacy_status,
            "message": "Publicación simulada exitosa. Configura client_secrets.json para subir a tu canal real."
        }

    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        from google_auth_oauthlib.flow import InstalledAppFlow

        scopes = ["https://www.googleapis.com/auth/youtube.upload"]
        flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), scopes)
        credentials = flow.run_local_server(port=0)
        youtube = build("youtube", "v3", credentials=credentials)

        body = {
            "snippet": {
                "title": title[:100],
                "description": description,
                "tags": tags,
                "categoryId": "25"
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False
            }
        }

        media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        response = request.execute()

        video_id = response.get("id")
        return {
            "status": "published",
            "video_id": video_id,
            "url": f"https://youtube.com/shorts/{video_id}"
        }
    except Exception as e:
        print(f"[YouTube Uploader] Error durante la subida: {e}")
        return {"status": "error", "error": str(e)}
