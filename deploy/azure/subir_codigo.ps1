# Empaqueta la carpeta del proyecto, la sube a la VPS e instala/actualiza.
# No sube output/, .git, la base de datos ni secretos. En la VPS no se pisan data/ ni .env.
# Uso:  powershell -ExecutionPolicy Bypass -File deploy\azure\subir_codigo.ps1
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\config.ps1"
$destino = Destino
$raiz = (Resolve-Path "$PSScriptRoot\..\..").Path
$paquete = Join-Path $env:TEMP "fabrica.tgz"

Write-Host "Empaquetando $raiz ..."
tar.exe -czf $paquete -C $raiz --exclude=.git --exclude=output --exclude=__pycache__ `
  --exclude=data/fabrica.db --exclude=data/canales --exclude=data/ajustes.json `
  --exclude=.env --exclude=client_secrets.json --exclude=cookies.txt .
if ($LASTEXITCODE -ne 0) { throw "Falló tar" }

Write-Host "Subiendo a $destino ..."
scp $paquete "${destino}:/tmp/fabrica.tgz"
# sed quita los saltos de línea de Windows (CRLF) por si algún editor los añadió
ssh -t $destino "mkdir -p /tmp/fx && tar -xzf /tmp/fabrica.tgz -C /tmp/fx ./deploy/actualizar.sh && sed -i 's/\r`$//' /tmp/fx/deploy/actualizar.sh && sudo bash /tmp/fx/deploy/actualizar.sh /tmp/fabrica.tgz && rm -rf /tmp/fx"
Remove-Item $paquete
Write-Host "Código actualizado y servicio reiniciado."
