#!/usr/bin/env bash
# Grants read access to ONLY the existing non-secret historical cost ledger.
set -euo pipefail
if [[ "${1:---check}" != --allow-backup-read || $# != 1 ]]; then
  echo 'Read-only check. Explicit --allow-backup-read is required to grant backup access to the legacy budget ledger.'
  exit 0
fi
[[ $EUID == 0 ]] || { echo 'Root approval is required.' >&2; exit 2; }
base=/var/lib/industrial-ai/artifacts
file="$base/mvp3/budget.json"
[[ -d "$base" && -d "$base/mvp3" && -f "$file" && ! -L "$base" && ! -L "$base/mvp3" && ! -L "$file" ]] || { echo 'Expected existing private state layout is missing or symlinked.' >&2; exit 2; }
command -v setfacl >/dev/null
setfacl -m u:industrial-backup:--x "$base" "$base/mvp3"
setfacl -m u:industrial-backup:r-- "$file"
echo 'Backup account may traverse the private directories and read only budget.json; no credential files were changed.'
