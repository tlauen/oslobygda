#!/usr/bin/env bash
# Backup av medlemsregister.db – kopierer til BACKUP_DIR med dato i filnamn.
# Les BACKUP_DIR frå .env i same mappe viss den finst; elles bruk miljøvariabel eller ~/Bygdelista-backup.
# Bruk: bash backup.sh   (stå i medlemsregister/)

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/.env" ]]; then
  set -a
  source "${SCRIPT_DIR}/.env"
  set +a
fi
DB="${SCRIPT_DIR}/medlemsregister.db"
BACKUP_DIR="${BACKUP_DIR:-$HOME/Bygdelista-backup}"
KEEP_N=30

if [[ ! -f "$DB" ]]; then
  echo "Database finst ikkje: $DB" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
STAMP=$(date +%Y-%m-%d-%H%M)
DEST="${BACKUP_DIR}/medlemsregister-${STAMP}.db"
cp "$DB" "$DEST"
echo "Backup: $DEST"

# Behald berre dei KEEP_N nyaste backupane
cd "$BACKUP_DIR" || exit 0
ls -t medlemsregister-*.db 2>/dev/null | tail -n +$((KEEP_N + 1)) | while read -r f; do rm -f "$f"; done
