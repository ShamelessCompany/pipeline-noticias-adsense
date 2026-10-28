# Abre la sala de control de la VPS en tu navegador a través de un túnel SSH.
# El panel nunca queda expuesto a internet: solo escucha en localhost de la VPS.
# Deja esta ventana abierta mientras uses el panel (Ctrl+C para cerrar).
. "$PSScriptRoot\config.ps1"
$destino = Destino
Start-Job { Start-Sleep 3; Start-Process "http://localhost:5050" } | Out-Null
Write-Host "Túnel abierto: http://localhost:5050  (Ctrl+C para cerrar)"
ssh -N -L 5050:localhost:5050 $destino
