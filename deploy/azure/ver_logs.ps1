# Muestra en vivo lo que hace la fábrica en la VPS (Ctrl+C para salir).
. "$PSScriptRoot\config.ps1"
ssh -t (Destino) "journalctl -u fabrica -f -n 100"
