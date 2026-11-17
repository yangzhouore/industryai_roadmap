#!/usr/bin/env bash
# Build only. Never selects a release, starts services or enables timers.
set -euo pipefail
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ "${1:---check}" != --prepare || $# != 2 ]]; then
  echo 'Read-only check: --prepare /srv/industrial-ai/releases/<40-character-commit> builds a NEW approved checkout.'
  exit 0
fi
exec python3.12 "$here/prepare_release.py" --prepare "$2"
