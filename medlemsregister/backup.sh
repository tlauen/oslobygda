#!/usr/bin/env bash
# Bakoverkompatibel inngang. Brukar konsistent backup med kontrollert gjenoppretting.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${BYGDELISTA_PYTHON:-python3}"
exec "$PYTHON" "${SCRIPT_DIR}/backup_kommando.py" "$@"
