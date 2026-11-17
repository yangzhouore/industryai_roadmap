#!/usr/bin/env bash
# Explicit preparation only: no deployment, service start, timer enable or credential replacement.
set -euo pipefail
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
action="${1:---check}"
if [[ "$action" == --check ]]; then
  failed=0
  for command in node npm python3.12 psql pg_createcluster caddy systemctl age rclone; do
    if command -v "$command" >/dev/null 2>&1; then printf 'available: %s\n' "$command";
    else printf 'missing: %s\n' "$command"; failed=1; fi
  done
  printf 'No host changes made. Provisioning remains an explicit maintenance action.\n'
  exit "$failed"
fi
[[ "$action" == --provision && $# == 1 && $EUID == 0 ]] || { echo 'Use --check, or explicitly run --provision as root after approval.' >&2; exit 2; }
. /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 24.* ]] || { echo 'This recipe targets Ubuntu 24 LTS.' >&2; exit 2; }
for command in node npm python3.12 caddy systemctl; do command -v "$command" >/dev/null; done
[[ "$(node -p 'process.versions.node.split(".")[0]')" -ge 22 ]] || { echo 'Node 22+ required.' >&2; exit 2; }
getent group industrial-ai >/dev/null || groupadd --system industrial-ai
for account in industrial-web industrial-worker industrial-backup industrial-build; do
  id "$account" >/dev/null 2>&1 || useradd --system --gid industrial-ai --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin "$account"
done
install -d -m 0750 -o root -g industrial-ai /srv/industrial-ai /srv/industrial-ai/releases /var/lib/industrial-ai
install -d -m 0700 -o industrial-worker -g industrial-ai /var/lib/industrial-ai/artifacts
install -d -m 0700 -o industrial-backup -g industrial-ai /var/lib/industrial-ai/backups
install -d -m 0700 -o industrial-build -g industrial-ai /var/lib/industrial-ai/build
install -d -m 0750 -o caddy -g caddy /var/log/industrial-ai
install -d -m 0700 /etc/industrial-ai
for example in "$here"/environment/*.env.example; do
  target="/etc/industrial-ai/$(basename "$example" .example)"
  if [[ ! -e "$target" && ! -L "$target" ]]; then install -m 0600 "$example" "$target"; fi
done
install -d -m 0755 /etc/systemd/system/caddy.service.d /etc/systemd/journald.conf.d
for unit in "$here"/systemd/*.service "$here"/systemd/*.timer; do
  target="/etc/systemd/system/$(basename "$unit")"
  [[ ! -e "$target" ]] || cmp -s "$unit" "$target" || { echo 'Existing unit differs; review it manually before replacement.' >&2; exit 2; }
  install -m 0644 "$unit" "$target"
done
for pair in 'systemd/caddy.service.d/industrial-ai.conf:/etc/systemd/system/caddy.service.d/industrial-ai.conf' 'journald.conf:/etc/systemd/journald.conf.d/industrial-ai.conf' 'Caddyfile:/etc/caddy/industrial-ai.Caddyfile'; do
  source_file="$here/${pair%%:*}"; target="${pair#*:}"
  [[ ! -e "$target" ]] || cmp -s "$source_file" "$target" || { echo 'Existing service configuration differs; manual review required.' >&2; exit 2; }
  install -m 0644 "$source_file" "$target"
done
systemctl daemon-reload
printf 'Prepared inactive configuration. No services started or timers enabled; credentials remain operator-supplied.\n'
