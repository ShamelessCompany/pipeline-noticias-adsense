# Copia .env, client_secrets.json y cookies.txt (los que existan en la carpeta del proyecto) a la VPS.
# Viajan cifrados por SSH y quedan con permisos 600 para el usuario 'fabrica'.
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\config.ps1"
$destino = Destino
$raiz = (Resolve-Path "$PSScriptRoot\..\..").Path
$subidos = @()
foreach ($f in ".env", "client_secrets.json", "cookies.txt") {
  $ruta = Join-Path $raiz $f
  if (Test-Path $ruta) { scp $ruta "${destino}:/tmp/$f"; $subidos += $f }
}
if (-not $subidos) { Write-Host "No encontré .env, client_secrets.json ni cookies.txt en $raiz"; exit 1 }
$cmds = ($subidos | ForEach-Object { "sudo install -o fabrica -g fabrica -m 600 /tmp/$_ /opt/fabrica/app/$_ && rm /tmp/$_" }) -join " && "
ssh -t $destino "$cmds && sudo systemctl restart fabrica"
Write-Host "Subidos: $($subidos -join ', '). Servicio reiniciado."
