# Crea la VPS en Azure (Ubuntu 24.04, solo SSH abierto y solo para tu IP).
# Requiere Azure CLI: winget install Microsoft.AzureCLI
# Uso:  powershell -ExecutionPolicy Bypass -File deploy\azure\crear_vm.ps1
param(
  [string]$Region = "eastus",          # la región suele cambiar poco el precio; eastus es de las baratas
  [string]$Tamano = "Standard_B2s",    # 2 vCPU, 4 GB. Si los renders van lentos: Standard_D2as_v5
  [int]$DiscoGB   = 64
)
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\config.ps1"

az account show *> $null
if ($LASTEXITCODE -ne 0) { az login | Out-Null }
Write-Host "Suscripción activa:" (az account show --query name -o tsv)

az group create -n $GRUPO -l $Region -o none
Write-Host "Creando la VM $VM_NOMBRE ($Tamano) en $Region..."
$vm = az vm create -g $GRUPO -n $VM_NOMBRE `
  --image Canonical:ubuntu-24_04-lts:server:latest --size $Tamano `
  --admin-username $VM_USER --generate-ssh-keys `
  --os-disk-size-gb $DiscoGB --storage-sku StandardSSD_LRS `
  --public-ip-sku Standard --nsg-rule SSH -o json | ConvertFrom-Json
$ip = $vm.publicIpAddress

# SSH solo desde tu IP actual (si cambia, ejecuta permitir_mi_ip.ps1)
& "$PSScriptRoot\permitir_mi_ip.ps1"

(Get-Content "$PSScriptRoot\config.ps1") -replace '^\$VM_IP\s*=.*', "`$VM_IP     = `"$ip`"" |
  Set-Content "$PSScriptRoot\config.ps1"
Write-Host ""
Write-Host "VM lista en $ip. Siguiente paso: deploy\azure\subir_codigo.ps1"
