# Conecta un canal de YouTube a la fábrica que corre en la VPS.
# Abre un túnel en el puerto 8765 y lanza el asistente OAuth allí; tú solo abres el enlace que imprime.
# Uso:  powershell -ExecutionPolicy Bypass -File deploy\azure\conectar_canal.ps1 curiosidades
param([Parameter(Mandatory = $true)][string]$Alias)
. "$PSScriptRoot\config.ps1"
$destino = Destino
Write-Host "Cuando aparezca el enlace, ábrelo en tu navegador, entra con la cuenta dueña del canal y elige el canal."
ssh -t -L 8765:localhost:8765 $destino "cd /opt/fabrica/app && sudo -u fabrica /opt/fabrica/venv/bin/python fabrica.py conectar-canal $Alias"
