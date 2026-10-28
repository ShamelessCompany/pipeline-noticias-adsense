# Fábrica de Contenido

Agentes que producen videos para YouTube en varios nichos a la vez, en tu PC o en una VPS, con costo cero.
Hay dos líneas de producción:

1. **Clips.** De un VOD de Twitch o un video de YouTube, el bot encuentra los momentos graciosos, las anécdotas o los picos de reacción. Después los recorta en vertical, les pone título en pantalla y subtítulos, y decide título, descripción y tags.
2. **Originales.** A partir de un tema o de un video de referencia, el bot investiga, escribe un guion propio con el estilo de los canales que más funcionan en ese nicho y lo limpia de muletillas de IA. Luego le pone voz y subtítulos y lo monta con B-roll libre.

Todo pasa por una **sala de control** web donde ves a cada agente trabajar, revisas y apruebas las piezas, y configuras nichos, fuentes y modelos.

El pipeline de noticias original (`main.py`, `app.py`, `src/`) sigue funcionando igual. La fábrica reutiliza su configuración de FFmpeg y su preprocesado de voz.

## Arrancar

```powershell
pip install -r requirements.txt
python fabrica.py panel
```

Abre http://127.0.0.1:5050. El trabajador arranca encendido y procesa la cola.

Sin ninguna clave la fábrica ya funciona, con guiones de respaldo simples y tarjetas generadas como imagen. Para que escriba bien necesitas un modelo de lenguaje gratuito (ver abajo).

## Modelos de lenguaje (gratis)

En **Ajustes** eliges el orden. Se usa el primero que responda:

| Proveedor | Qué necesitas |
|---|---|
| `gemini` | Una clave de Google AI Studio (aistudio.google.com/apikey). La suscripción Gemini Pro de la app no da acceso a la API, pero la clave de AI Studio tiene capa gratuita. |
| `opencode` | Una clave de OpenCode Zen y el nombre de uno de sus modelos gratuitos (la lista cambia; está en su web). |
| `ollama` | Ollama instalado en tu máquina (`ollama pull llama3.1`). No necesita clave ni internet. |
| `local` | Nada. Usa reglas y plantillas de respaldo, con calidad básica. |

El botón **Probar conexión** te dice cuál responde.

## Cómo trabaja el bot

| Agente | Qué hace |
|---|---|
| Explorador | Revisa las fuentes activas y los temas semilla, y crea trabajos sin pasarse del cupo diario de cada nicho. |
| Clipper | Mide la energía del audio, lee la transcripción y le pide al modelo que puntúe los candidatos. Se queda con los mejores. |
| Analista de estilo | Estudia los videos más vistos de los canales de referencia y guarda el patrón: ganchos, estructura y fórmulas de título. Con «Analizar edición» también mide cómo editan (ver abajo). |
| Guionista | Investiga en Wikipedia, escribe con otro ángulo distinto al de la referencia y pasa el texto por el filtro anti-IA. |
| Locutor | Pone la voz con Edge-TTS y saca los subtítulos palabra por palabra con Whisper. |
| Editor | Es el Director de montaje: parte cada escena en planos al ritmo del nicho y mete insertos justo cuando se dicen las cosas (cifras, fotos, lugares, citas), con zooms, efectos de sonido, subtítulos y música. |
| Empaquetador | Escribe título, descripción y tags, y añade los créditos. |
| Revisor | Comprueba las normas de monetización y bloquea lo que tiene riesgo. |
| Publicador | Reparte lo aprobado en los horarios de cada nicho y lo sube a su hora. |

Estados de un trabajo: `en_cola → procesando → revision → aprobado → programado → publicado`.

## Edición como los canales de referencia

La fábrica no copia material de otros canales. Aprende **cómo editan** y edita igual con material libre o propio.

1. **Analista de edición.** En *Nichos → Analizar edición* (o `python fabrica.py edicion NICHO`) baja a 360p los 2 videos más vistos de cada canal de referencia (Shorts y largos por separado), mide cortes por minuto, largo medio de plano y golpes de sonido. Con una clave de Gemini, además mira un fotograma después de cada corte y cuenta qué usan: B-roll, cifras en pantalla, fotos enmarcadas, mapas, zooms. Después borra los videos. Queda la **receta** del nicho en `data/estilos/<nicho>.json`. Sin receta se usa una por defecto para cada formato.
2. **Director de montaje** (`fabrica/montaje.py`). Alinea el guion con los tiempos de cada palabra de la locución y decide:
   - cuántos planos lleva cada escena según el ritmo de la receta;
   - qué inserto va en cada momento: el modelo de lenguaje propone y unas reglas completan (un número → cifra grande, un nombre propio → su foto enmarcada, «en París» → rótulo de lugar, texto entre comillas → cita);
   - zoom de golpe en las cifras y citas, y *whoosh*/*pop* en parte de los cortes e insertos.
3. **Biblioteca de recursos** (pestaña *Biblioteca*). El Editor busca ahí primero. Todo lo que baja de Pexels, Pixabay, Openverse, Wikimedia Commons o NASA se guarda con su licencia y su autor para reutilizarlo, y puedes subir tu propio material. Solo se aceptan licencias de uso comercial que dejan modificar (CC0, dominio público, CC BY, CC BY-SA, Pexels, Pixabay, NASA, propio). NC y ND se rechazan.
4. **Gráficos y efectos generados** (`fabrica/graficos.py`): cifras, palabras clave, rótulos, citas, lugares y marcos de foto como capas PNG, y efectos de sonido sintetizados con FFmpeg. No dependen de nadie, así que no tienen riesgo de derechos.

El Revisor añade la comprobación «Recursos con licencia» y bloquea si algo no tiene licencia válida. Los créditos de todo lo usado van a la descripción.

**Búsqueda por significado (opcional).** Por defecto la biblioteca busca por palabras. Con `pip install sentence-transformers` y *Biblioteca → Calcular índice* (o `python fabrica.py biblioteca indice`) entiende frases en español contra el contenido real de las imágenes (CLIP). La primera vez baja unos 600 MB de modelos. En una B2s va justo; mejor activarlo en el PC.

**Material propio en bloque:** copia la carpeta dentro del proyecto y ejecuta
`python fabrica.py biblioteca importar assets/biblioteca/propios/mis_fotos --licencia propio --credito "Tu nombre"`.
Las etiquetas salen del nombre del archivo y de sus carpetas, así que conviene nombrarlos por lo que se ve (`emu_corriendo_desierto.mp4`).

## Normas de monetización (lo que comprueba el Revisor)

- **Clips:** la fuente tiene que estar en *Fuentes* con «permite clips», o marcada a mano. Sin permiso, el clip queda **bloqueado**. El Revisor también pide aporte propio visible (título en pantalla, subtítulos y una intro narrada con contexto) y crédito con enlace al creador.
- **Originales:** menos del 12 % de frases de 5 palabras coincidentes con la referencia (con 25 % o más, bloquea), una extensión mínima, un puntaje de escritura humana de 70 o más y una voz real (no simulada).
- Por defecto la **aprobación es manual**. YouTube pide que los canales automatizados tengan supervisión humana real. Puedes activar la autoaprobación con un umbral en *Ajustes*, pero lo bloqueado nunca se aprueba solo.

## Publicar

Por defecto la publicación es **simulada**: no se sube nada, solo queda anotado qué y cuándo se publicaría.
Para subir de verdad:

1. Crea credenciales OAuth de escritorio en Google Cloud con la YouTube Data API v3 activada.
2. Guarda el archivo como `client_secrets.json` en esta carpeta.
3. Cambia *Ajustes → Publicación* a «Real».

La primera subida abre el navegador para autorizar y guarda el token en `data/youtube_token.json`.

## Línea de comandos (útil en una VPS)

```bash
python fabrica.py panel --host 0.0.0.0     # panel accesible desde fuera (ponle un túnel o una contraseña delante)
python fabrica.py trabajador               # solo el trabajador, sin interfaz
python fabrica.py ciclo                    # una pasada y termina (para cron)
python fabrica.py clip URL --nicho clips_streams --permiso
python fabrica.py original "tema" --nicho curiosidades --formato largo
python fabrica.py estilo curiosidades
python fabrica.py edicion curiosidades           # mide cortes e insertos de los canales de referencia
python fabrica.py biblioteca buscar "emú corriendo"
python fabrica.py conectar-canal curiosidades   # OAuth de un canal (en VPS, con túnel en el puerto 8765)
python fabrica.py canales
```

Ejemplo de cron cada hora: `0 * * * * cd /ruta/al/proyecto && python fabrica.py ciclo >> fabrica.log 2>&1`

## En la nube 24/7 (Azure)

La guía completa está en [`deploy/azure/README_AZURE.md`](deploy/azure/README_AZURE.md). En resumen, desde PowerShell:

```powershell
deploy\azure\crear_vm.ps1          # VM Ubuntu B2s, solo SSH y solo desde tu IP
deploy\azure\subir_codigo.ps1      # instala y deja la fábrica como servicio
deploy\azure\subir_secretos.ps1    # .env, client_secrets.json, cookies.txt
deploy\azure\conectar_canal.ps1 curiosidades   # un canal de YouTube por alias
deploy\azure\abrir_panel.ps1       # panel en http://localhost:5050 por túnel SSH
```

Cada nicho publica en el canal de su campo «Canal de YouTube (alias)». Si se agota la cuota diaria de YouTube,
el Publicador lo reintenta al día siguiente.

## Archivos

```
fabrica.py            entrada (panel, trabajador, ciclo, clip, original, estilo)
fabrica_app.py        servidor de la sala de control
templates/fabrica.html  interfaz
fabrica/              núcleo: cola (db), llm, estilo (anti-IA), media, subtítulos, B-roll, cumplimiento…
fabrica/agentes/      explorador, clipper, guionista, analista, publicador
data/nichos.json      nichos (editable desde el panel)
data/fuentes.json     canales que vigila el Explorador
data/estilos/         patrones aprendidos por nicho
data/fabrica.db       cola y bitácora (SQLite)
output/trabajos/NNNNN/  todo lo que genera cada trabajo (final.mp4, mini.jpg, subtítulos…)
assets/musica/<nicho>/  pon aquí música libre de derechos; el Editor la mezcla con ducking
assets/biblioteca/    recursos libres y propios (los indexa la biblioteca) y efectos generados
```

## Límites actuales

- El reencuadre vertical de clips centra la imagen con fondo desenfocado. Todavía no sigue caras.
- El Clipper no lee el chat de Twitch. Decide por audio, transcripción y modelo de lenguaje.
- Transcribir un VOD largo con Whisper en CPU es lento. Si el video de YouTube ya tiene subtítulos, se usan esos.
- Las claves se guardan en `.env` en texto plano. No compartas esa carpeta tal cual.
