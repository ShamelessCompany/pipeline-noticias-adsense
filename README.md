# Pipeline de Noticias Automatizadas (Cumplimiento AdSense & YouTube Shorts)

> **Ubicación del Proyecto:** `D:\Programacion\PipelineNoticiasAdsense`  
> **Formato de Salida:** Vertical 9:16 (`1080x1920`) a 30 FPS optimizado para YouTube Shorts y TikTok.  
> **Enfoque de Monetización:** 100% alineado con las directrices del **YouTube Partner Program (YPP)** y **Google AdSense**.

---

## 1. Cumplimiento de Políticas de Monetización (AdSense / YPP)

La gran mayoría de canales de noticias automatizados sufren desmonetización por dos motivos:
1. **Contenido Reutilizado (*Reused Content*):** Tomar titulares, noticias o capturas de terceros sin aportar valor editorial significativo, análisis crítico o contraste de fuentes.
2. **Contenido Repetitivo (*Repetitive/Templated Content*):** Videos masivos donde solo cambia un texto plano sobre un fondo estático o un gameplay continuo.

### Mecanismos de Protección Integrados:
* **Transformación Editorial Real:** El generador de guiones no parafrasea; evalúa el impacto, compara posturas y genera un análisis crítico original con gancho y llamada a debate.
* **Edición Multicapa Dinámica:** Fondo con B-roll/procedural animado, tarjeta de noticia con animación suave de zoom/re-encuadre, mezcla de música con ducking y subtítulos palabra por palabra estilo karaoke.
* **Voz Neuronal Expresiva:** Síntesis con pausas sintácticas, entonación natural y dicción profesional con `edge-tts` en español neutro (`es-MX-DaliaNeural` o `es-ES-AlvaroNeural`).
* **Checkpoint de Curación Humana:** Panel interactivo local (`output/checkpoint.html`) y notificación webhook de Discord para que un humano valide y apruebe el video antes de su publicación oficial.

---

## 2. Arquitectura del Pipeline

```
[Fuentes: X/Twitter, News APIs, Reddit]
              │
              ▼
    [Scraper: Playwright]
   (Captura limpia en Dark Mode, sin cookies)
              │
              ▼
    [Motor de Guion: Gemini]
   (Aplica filtros de valor editorial y retención)
              │
              ▼
    [Síntesis de Voz: Edge-TTS]
   (Generación de audio neuronal en español)
              │
              ▼
    [Subtítulos: Faster-Whisper]
   (Generación de archivo .ass con efecto karaoke)
              │
              ▼
    [Compositor: FFmpeg / Remotion]
   (Cortes, escalado 9:16 o 16:9, zoom, B-roll)
              │
              ▼
    [Revisión Humana en Discord / Dashboard Local]
              │
         [Aprobado] ──► [YouTube Data API Upload]
```

---

## 3. Requisitos del Sistema e Instalación

### Requisitos Previos:
* **Python 3.10 a 3.14 (64-bit)**
* **Git** instalado
* **FFmpeg:** El proyecto incluye soporte automático mediante `imageio-ffmpeg` (sin necesidad de configurar variables de entorno en Windows). Si prefieres el FFmpeg del sistema, puedes instalarlo con:
  ```powershell
  winget install Gyan.FFmpeg.Essentials
  ```

### Paso 1: Clonar / Acceder al Repositorio
```powershell
cd D:\Programacion\PipelineNoticiasAdsense
```

### Paso 2: Instalar Dependencias de Python
```powershell
pip install -r requirements.txt
```

Las dependencias principales son:
* `playwright`: Motor de automatización de navegador headless para capturas nítidas.
* `edge-tts`: Síntesis de voz neuronal gratuita y de alta calidad.
* `faster-whisper`: Reconocimiento de voz y marcas de tiempo por palabra acelerado por CPU/GPU.
* `imageio-ffmpeg`: Binario FFmpeg con soporte para códec H.264 y filtros de subtítulos `libass`.
* `google-genai`: Integración con modelos Gemini para guiones editoriales.
* `pillow`, `requests`, `pydantic`.

### Paso 3: Instalar el Navegador para Playwright
```powershell
python -m playwright install chromium
```

---

## 4. Configuración (.env y config.json)

Copia el archivo de ejemplo:
```powershell
cp .env.example .env
```

Edita `.env` con tus preferencias:
```ini
# Opcional: Clave para guiones con IA en tiempo real (gratuita en aistudio.google.com)
# Si se deja vacía, el pipeline usa el motor editorial determinístico de respaldo.
GEMINI_API_KEY=tu_clave_aqui

# Opcional: Webhook de Discord para el canal #revision-shorts
DISCORD_WEBHOOK_URL=

# Configuración de voz Edge-TTS
VOICE_NAME=es-MX-DaliaNeural
VOICE_RATE=+0%
VOICE_PITCH=+0Hz
```

En `config.json` puedes ajustar:
* Dimensiones del video (`1080x1920` por defecto).
* Modelo de Whisper (`base` para máxima precisión o `tiny` para máxima velocidad).
* Estilos de subtítulos (fuente, colores ASS, margen inferior para evitar botones de YouTube).

---

## 5. Ejecución

### Opción A: Estudio Visual Web Interactivo (Recomendado para Edición y Revisión)
Inicia la interfaz gráfica completa en tu navegador local (`http://127.0.0.1:5000`):
```powershell
python app.py
# O alternativamente:
python main.py studio
```
**Características del Estudio Visual:**
* **Entrada de Noticias y Enlaces:** Pega URLs públicas (tweets, notas) o ingresa titulares y fragmentos.
* **Taller de Guion con Tonalidades Contextuales:** Selector de 4 presets (*Última Hora*, *Investigación*, *Polémica*, *Futurista*) + campo para dar instrucciones personalizadas a la IA para retocar el texto y las pausas.
* **Control de Voz y Locución:** Selector de voces neuronales, ajuste de velocidad/tono, clonación local con muestra `.wav` y escucha previa inmediata del audio generado.
* **Vista Previa en Vivo:** Reproductor vertical 9:16 que muestra la tarjeta, la pista de audio y el video final compilado con subtítulos karaoke listos para descargar o aprobar.
* **Ejecución Paso a Paso o en Cascada:** Puedes ejecutar cada fase por separado para retocar lo justo y necesario o pulsar *"Ejecutar Todo el Pipeline en Cascada"*.

### Opción B: Ejecutar la Demo por Consola
Genera un video completo de demostración en ~60 segundos desde la terminal:
```powershell
python demo.py
```

Archivos generados en la carpeta `output/`:
* `output/demo_short.mp4`: Video vertical 9:16 listo para YouTube Shorts.
* `output/news_card.png`: Captura en Modo Oscuro renderizada con Playwright.
* `output/voiceover.mp3`: Pista de voz neuronal.
* `output/subtitles.ass`: Subtítulos con efecto karaoke sincronizado palabra a palabra.
* `output/checkpoint.html`: Dashboard interactivo de revisión humana.

### Opción B: Ejecutar con Noticia Personalizada
```powershell
python main.py run --topic "NVIDIA anuncia nueva arquitectura cuántica" --content "El nuevo chip reduce un 90% el consumo energético en servidores de IA."
```

O capturando directamente una URL pública:
```powershell
python main.py run --topic "Nuevo hito aeroespacial" --url "https://ejemplo.com/noticia"
```

### Opción C: Checkpoint de Revisión Humana
Abre el dashboard en tu navegador para revisar el video y su análisis de cumplimiento AdSense:
```powershell
Start-Process "output\checkpoint.html"
```

### Opción D: Subir a YouTube Shorts
Una vez configurado `client_secrets.json` de Google Cloud Console:
```powershell
python main.py upload --video "output\demo_short.mp4" --title "Revolución en Estándares de IA" --privacy unlisted
```

---

## 6. Estructura del Proyecto

```
D:\Programacion\PipelineNoticiasAdsense\
├── .gitignore                  # Exclusiones de Git (temporales, videos pesados, secrets)
├── .env.example                # Plantilla de variables de entorno
├── config.json                 # Configuración de resolución, tipografías y TTS
├── requirements.txt            # Dependencias del proyecto
├── demo.py                     # Demo funcional de extremo a extremo
├── main.py                     # Interfaz CLI principal
├── src/
│   ├── __init__.py
│   ├── config.py               # Detección de FFmpeg y compatibilidad PyAV/Whisper
│   ├── scraper.py              # Captura de pantalla dark-mode con Playwright
│   ├── script_generator.py     # Generador de guiones con filtros anti-reused content
│   ├── voice_synthesizer.py    # Locución neuronal con Edge-TTS
│   ├── subtitle_generator.py   # Subtítulos .ASS con karaoke palabra a palabra
│   ├── video_compositor.py     # Ensamblado multicapa 9:16 con FFmpeg
│   ├── review_checkpoint.py    # Dashboard web local y alertas Discord
│   └── youtube_uploader.py     # Módulo de subida a YouTube Data API v3
├── assets/
│   ├── audio/                  # Pistas de música de fondo opcionales
│   └── broll/                  # Clips de archivo B-roll opcionales
└── output/                     # Artefactos producidos por el pipeline
    ├── demo_short.mp4
    ├── news_card.png
    ├── voiceover.mp3
    ├── subtitles.ass
    └── checkpoint.html
```

---

## 7. Instrucciones para Subir a Git

El repositorio ya cuenta con `git init` configurado y un `.gitignore` estricto que protege claves privadas y archivos temporales. Para subirlo a tu cuenta de GitHub o GitLab:

```powershell
cd D:\Programacion\PipelineNoticiasAdsense

# 1. Agregar los archivos al control de versiones
git add .

# 2. Realizar el primer commit
git commit -m "feat: initial commit - pipeline de noticias automatizadas con cumplimiento AdSense"

# 3. Vincular con tu repositorio remoto (reemplaza con tu URL)
git remote add origin https://github.com/TU_USUARIO/pipeline-noticias-adsense.git

# 4. Cambiar a rama main y subir
git branch -M main
git push -u origin main
```
