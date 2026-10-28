# Fábrica de Contenido 24/7 en Azure

La idea: una VPS Ubuntu en Azure corre la fábrica como servicio. El panel solo escucha dentro de la VPS
y tú entras desde tu PC por un túnel SSH. El Explorador busca material solo, los agentes producen,
tú apruebas desde el panel y el Publicador sube a cada canal en sus horarios.

Todo se hace desde PowerShell en tu PC, en la carpeta `D:\Programacion\PipelineNoticiasAdsense`.
Los scripts están en `deploy\azure\`. Si PowerShell bloquea los scripts, ejecútalos así:
`powershell -ExecutionPolicy Bypass -File deploy\azure\NOMBRE.ps1`.

---

## 0. Qué VM y cuánto cuesta

| Opción | Para qué | Precio aprox. (Linux, eastus, pago por uso) |
|---|---|---|
| **Standard_B2s** (2 vCPU, 4 GB) | Recomendada para empezar: unos 5–10 Shorts al día con Whisper `base` | ~30 USD/mes |
| Standard_D2as_v5 (2 vCPU, 8 GB) | Si produces mucho o haces videos largos (CPU sin límite de créditos) | ~65 USD/mes |
| Disco 64 GB Standard SSD + IP pública | Siempre | ~8 USD/mes |

- Con **Azure for Students** (lo da el GitHub Student Pack) tienes 100 USD de crédito sin tarjeta: unos 2–3 meses de B2s.
- Las B-series acumulan "créditos de CPU". Si la fábrica renderiza sin parar, se gastan y la CPU baja a ~40 %.
  Lo notarás porque los trabajos tardan el doble. Para cambiar de tamaño sin reinstalar:
  `az vm resize -g rg-fabrica -n vm-fabrica --size Standard_D2as_v5`.
- La B1s gratuita (1 GB de RAM) se queda corta para Whisper y FFmpeg.
- Comprueba el precio real en https://azure.microsoft.com/pricing/calculator/ antes de crear nada.

## 1. Crear la VM

1. Instala Azure CLI: `winget install Microsoft.AzureCLI` y abre una terminal nueva.
2. Ejecuta `deploy\azure\crear_vm.ps1`. Te pide iniciar sesión en Azure y crea:
   - Grupo `rg-fabrica`, VM `vm-fabrica` con Ubuntu 24.04, usuario `sena`, llave SSH en `~\.ssh\id_rsa`.
   - Solo el puerto 22 abierto, y solo para tu IP actual.
   - Guarda la IP en `deploy\azure\config.ps1`.
3. Si tu IP de casa cambia y SSH deja de responder: `deploy\azure\permitir_mi_ip.ps1`.

Parámetros opcionales: `-Region westeurope`, `-Tamano Standard_D2as_v5`, `-DiscoGB 128`.

## 2. Subir e instalar la fábrica

```powershell
deploy\azure\subir_codigo.ps1
```

Empaqueta la carpeta (sin `output\`, `.git`, base de datos ni secretos), la sube y ejecuta `deploy/instalar.sh` en la VPS, que:
- instala Python, FFmpeg y fuentes, y añade 4 GB de swap;
- crea el usuario `fabrica` y deja todo en `/opt/fabrica/app` con su entorno en `/opt/fabrica/venv`;
- registra el servicio `fabrica` (arranca solo al encender y se reinicia si se cae);
- programa una actualización semanal de yt-dlp y una copia diaria de `data/` en `/opt/fabrica/backups`;
- activa el cortafuegos dejando solo SSH;
- en la primera instalación deja el **piloto automático encendido** y la **aprobación manual activada**.

Para actualizar el código más adelante, ejecuta lo mismo. No se pisan la cola, los canales, los ajustes ni el `.env` de la VPS.

## 3. Secretos

Pon en la carpeta del proyecto (en tu PC) los que tengas y ejecuta `deploy\azure\subir_secretos.ps1`:

| Archivo | Qué es |
|---|---|
| `.env` | `GEMINI_API_KEY`, `OPENCODE_API_KEY`, `PEXELS_API_KEY`, `PIXABAY_API_KEY`, y opcionalmente `PANEL_CLAVE` (ver 6) y `YTDLP_COOKIES=/opt/fabrica/app/cookies.txt` |
| `client_secrets.json` | Credencial OAuth de Google para subir a YouTube (paso 4) |
| `cookies.txt` | Cookies de YouTube para yt-dlp (paso 5) |

También puedes poner las claves desde el panel, en Ajustes → Claves gratuitas.

## 4. Conectar canales de YouTube

### 4.1 Una sola vez: proyecto de Google Cloud

1. https://console.cloud.google.com → crea un proyecto (p. ej. "fabrica").
2. *APIs y servicios → Biblioteca* → activa **YouTube Data API v3**.
3. *Pantalla de consentimiento OAuth* → tipo **Externo**. Añade tu correo como usuario de prueba.
   Después pulsa **Publicar la app** (pasa a "En producción"). Así los tokens no caducan a los 7 días,
   que es lo que pasa en modo "Prueba". Google mostrará un aviso de "app no verificada" al conectar: es normal para uso propio.
4. *Credenciales → Crear credencial → ID de cliente OAuth → App de escritorio*. Descarga el JSON y guárdalo como
   `client_secrets.json` en la carpeta del proyecto. Luego ejecuta `subir_secretos.ps1`.

**Dos límites de YouTube que debes conocer:**
- **Videos privados hasta la auditoría.** Los proyectos de API nuevos que no han pasado la auditoría de YouTube
  suben los videos bloqueados como **privados**. Para publicar en público hay que pedir la auditoría gratuita
  (*YouTube API Services – Audit and Quota Extension Form*). Mientras tanto, deja la privacidad en «Privado»
  y publica a mano desde YouTube Studio, o espera la aprobación.
- **Cuota.** Cada proyecto tiene 10 000 unidades al día y una subida gasta unas 1 600, o sea unas **6 subidas diarias
  por proyecto**, contando todos los canales juntos. Si se agota, el Publicador reintenta al día siguiente.
  Para más volumen: pide ampliación en el mismo formulario o usa un proyecto de Google Cloud por cada pocos canales.

### 4.2 Por cada canal

```powershell
deploy\azure\conectar_canal.ps1 curiosidades
```

Abre un túnel en el puerto 8765 y lanza el asistente en la VPS. Abre el enlace que aparece, entra con la cuenta
dueña del canal y **elige el canal** (si la cuenta tiene varios, Google pregunta cuál). Al terminar verás
`Canal conectado: {... "titulo": "..."}`.

Después, en el panel → **Nichos**, escribe ese alias en «Canal de YouTube (alias)» de cada nicho que deba publicar ahí
y guarda. Puedes tener un canal por nicho o varios nichos en el mismo canal. Los canales conectados aparecen en Ajustes.

Por último, en Ajustes → Publicación, pon **Real**. Hasta entonces todo es simulado.

## 5. Fuentes de Twitch y YouTube

- **Twitch no necesita API ni claves.** yt-dlp lee los VODs públicos. En el panel → **Fuentes**, añade
  `https://www.twitch.tv/CANAL/videos?filter=archive`, uso «Clips», y marca **permite clips** solo si el streamer lo autoriza
  (en su panel o descripción, o por escrito). Guarda una captura de ese permiso. Los VODs de Twitch caducan a los 7–60 días,
  pero el Explorador revisa cada hora, así que llega a tiempo.
- **YouTube desde una VPS:** YouTube suele bloquear las IPs de centros de datos con "Sign in to confirm you're not a bot".
  Si en la bitácora ves ese error:
  1. En tu PC, con una **cuenta de Google secundaria** (no la de tus canales), abre YouTube en una ventana privada.
  2. Exporta las cookies en formato Netscape con una extensión como "Get cookies.txt LOCALLY" y guárdalas como `cookies.txt`.
  3. Añade `YTDLP_COOKIES=/opt/fabrica/app/cookies.txt` al `.env` y ejecuta `subir_secretos.ps1`.
  Las cookies caducan cada pocas semanas. Si el error vuelve, repite el proceso.

## 6. Usar el panel

```powershell
deploy\azure\abrir_panel.ps1
```

Se abre http://localhost:5050 a través del túnel. Deja esa ventana abierta mientras lo uses.
El panel no está expuesto a internet. Si quieres además usuario y contraseña (por ejemplo, si alguien más usa tu PC),
añade al `.env` `PANEL_USUARIO=admin` y `PANEL_CLAVE=una-clave-larga`.

Con la ventana cerrada la fábrica sigue trabajando: el túnel solo sirve para verla.

## 7. Operación diaria

| Quiero… | Cómo |
|---|---|
| Ver qué hace en vivo | `deploy\azure\ver_logs.ps1` o la Bitácora del panel |
| Reiniciar | `ssh sena@IP "sudo systemctl restart fabrica"` |
| Ver uso de disco | `ssh sena@IP "df -h /; du -sh /opt/fabrica/app/output"` |
| Recuperar una copia | `/opt/fabrica/backups/data-AAAA-MM-DD.tgz` (contiene `data/` y `.env`) |
| Apagar para no gastar | `az vm deallocate -g rg-fabrica -n vm-fabrica` (el disco sigue costando ~5 USD/mes) |
| Volver a encender | `az vm start -g rg-fabrica -n vm-fabrica` (la IP se mantiene: es estática) |
| Borrarlo todo | `az group delete -n rg-fabrica` (borra VM, disco e IP; no se puede deshacer) |

La limpieza automática borra cada hora los archivos intermedios de lo terminado hace más de 7 días
(`dias_retencion` en `data/ajustes.json`) y los VODs cuyos clips ya salieron. Se conservan `final.mp4` y la miniatura.

## Checklist de puesta en marcha

1. `crear_vm.ps1`
2. `subir_codigo.ps1`
3. Claves en `.env` y `subir_secretos.ps1`
4. `abrir_panel.ps1` → Ajustes → **Probar conexión** del modelo
5. Google Cloud (4.1) → `client_secrets.json` → `subir_secretos.ps1`
6. `conectar_canal.ps1 ALIAS` por cada canal → alias en cada nicho
7. Fuentes con permiso y temas semilla → el piloto automático hace el resto
8. Revisa y aprueba en el panel. Cuando confíes, pasa Publicación a «Real».
