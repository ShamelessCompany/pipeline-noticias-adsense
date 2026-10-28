# Deja entrar por SSH solo desde tu IP pública actual (útil si tu IP de casa cambia).
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\config.ps1"
$mi = (Invoke-RestMethod -Uri "https://api.ipify.org").Trim()
az network nsg rule update -g $GRUPO --nsg-name "${VM_NOMBRE}NSG" -n default-allow-ssh `
  --source-address-prefixes "$mi/32" -o none
Write-Host "SSH permitido solo desde $mi"
