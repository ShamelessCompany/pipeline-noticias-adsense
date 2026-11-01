# Crea la VPS en Azure (Ubuntu 24.04, solo SSH abierto y solo para tu IP).
# Requiere Azure CLI: winget install Microsoft.AzureCLI
# Uso:  powershell -ExecutionPolicy Bypass -File deploy\azure\crear_vm.ps1
param(
  # Azure for Students solo deja brazilsouth, northcentralus, canadacentral, westus2 y spaincentral
  # (política "Allowed resource deployment regions"). northcentralus es de las más baratas.
  [string]$Region = "northcentralus",
  [string]$Tamano = "Standard_B2als_v2", # 2 vCPU, 4 GB (la B2s no existe en northcentralus). Si los renders van lentos: Standard_D2as_v5
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
# az no corta el script al fallar: sin esta comprobación se anunciaría "VM lista" sin IP
if ($LASTEXITCODE -ne 0 -or -not $vm.publicIpAddress) {
  throw "No se pudo crear la VM. Revisa que la región y el tamaño estén permitidos: az vm list-skus -l $Region --size $Tamano -o table"
}
$ip = $vm.publicIpAddress

# SSH solo desde tu IP actual (si cambia, ejecuta permitir_mi_ip.ps1)
& "$PSScriptRoot\permitir_mi_ip.ps1"

(Get-Content "$PSScriptRoot\config.ps1") -replace '^\$VM_IP\s*=.*', "`$VM_IP     = `"$ip`"" |
  Set-Content "$PSScriptRoot\config.ps1"
Write-Host ""
Write-Host "VM lista en $ip. Siguiente paso: deploy\azure\subir_codigo.ps1"
