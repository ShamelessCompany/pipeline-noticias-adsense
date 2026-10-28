#!/usr/bin/env bash
# Lo llama subir_codigo.ps1 en la VPS: descomprime el paquete nuevo y reinstala.
set -euo pipefail
PAQUETE=${1:-/tmp/fabrica.tgz}
TMP=$(mktemp -d)
tar -xzf "$PAQUETE" -C "$TMP"
find "$TMP/deploy" -name "*.sh" -exec sed -i 's/\r$//' {} +
bash "$TMP/deploy/instalar.sh"
rm -rf "$TMP" "$PAQUETE"
