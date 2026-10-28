#!/usr/bin/env bash
# Instala o actualiza la Fábrica de Contenido en Ubuntu 24.04 (Azure u otra VPS).
# Uso (en la VPS, desde la carpeta donde subiste el código):  sudo bash deploy/instalar.sh
# Se puede repetir sin miedo: no toca data/ (cola, canales, ajustes) ni el .env que ya existan.
set -euo pipefail

ORIGEN="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAIZ=/opt/fabrica
APP=$RAIZ/app
VENV=$RAIZ/venv

if [[ $EUID -ne 0 ]]; then echo "Ejecuta con sudo"; exit 1; fi

echo "==> Paquetes del sistema"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip ffmpeg fonts-dejavu fonts-liberation \
  fontconfig curl ufw rsync tar >/dev/null

echo "==> Memoria de intercambio (Whisper y FFmpeg agradecen el margen)"
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "==> Usuario y carpetas"
id fabrica &>/dev/null || useradd --system --create-home --home-dir $RAIZ --shell /usr/sbin/nologin fabrica
mkdir -p $APP $RAIZ/cache $RAIZ/backups

echo "==> Copiando el código (sin pisar datos ni secretos)"
rsync -a --delete \
  --exclude '.git' --exclude '__pycache__' --exclude 'output/' --exclude 'data/' \
  --exclude '.env' --exclude 'client_secrets.json' --exclude 'cookies*.txt' \
  "$ORIGEN"/ $APP/
mkdir -p $APP/data $APP/output
for f in nichos.json fuentes.json; do
  [[ -f $APP/data/$f ]] || cp "$ORIGEN/data/$f" $APP/data/$f
done
# Primera instalación: piloto automático encendido para que trabaje solo
[[ -f $APP/data/ajustes.json ]] || echo '{"piloto_automatico": true, "aprobacion_manual": true}' > $APP/data/ajustes.json
[[ -f $APP/.env ]] || { [[ -f "$ORIGEN/.env" ]] && cp "$ORIGEN/.env" $APP/.env || touch $APP/.env; }
for f in client_secrets.json cookies.txt; do
  [[ -f "$ORIGEN/$f" ]] && cp "$ORIGEN/$f" $APP/$f || true
done
chown -R fabrica:fabrica $RAIZ
chmod 600 $APP/.env
[[ -f $APP/client_secrets.json ]] && chmod 600 $APP/client_secrets.json || true

echo "==> Entorno de Python"
[[ -d $VENV ]] || sudo -u fabrica python3 -m venv $VENV
sudo -u fabrica $VENV/bin/pip install -q --upgrade pip
sudo -u fabrica $VENV/bin/pip install -q -r $APP/requirements.txt

echo "==> Servicio"
cp $APP/deploy/fabrica.service /etc/systemd/system/fabrica.service
systemctl daemon-reload
systemctl enable fabrica >/dev/null
systemctl restart fabrica

echo "==> Tareas programadas (yt-dlp al día y copia de seguridad de data/)"
cat > /etc/cron.d/fabrica <<CRON
# yt-dlp se rompe cuando YouTube/Twitch cambian algo: actualizar cada lunes
15 4 * * 1 fabrica $VENV/bin/pip install -q -U yt-dlp && sudo systemctl restart fabrica
# Copia diaria de la cola, canales, nichos y ajustes (se guardan 14)
30 3 * * * root tar -czf $RAIZ/backups/data-\$(date +\%F).tgz -C $APP data .env && ls -1t $RAIZ/backups/data-*.tgz | tail -n +15 | xargs -r rm
CRON
# El reinicio semanal lo hace root: dar permiso a ese único comando
echo "fabrica ALL=(root) NOPASSWD: /usr/bin/systemctl restart fabrica" > /etc/sudoers.d/fabrica
chmod 440 /etc/sudoers.d/fabrica

echo "==> Cortafuegos: solo SSH"
ufw allow OpenSSH >/dev/null
ufw --force enable >/dev/null

sleep 3
systemctl --no-pager --lines=5 status fabrica || true
echo
echo "Listo. Desde tu PC abre el panel con deploy/azure/abrir_panel.ps1 (túnel SSH a localhost:5050)."
