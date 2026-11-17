#!/usr/bin/env bash
# Only creates a NEW dedicated private cluster. Never changes another cluster.
set -euo pipefail
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
[[ "${1:---check}" == --provision && $# == 1 ]] || { echo 'Dry check: explicit --provision is required to create the dedicated cluster.'; exit 0; }
[[ $EUID == 0 ]] || { echo 'Root is required for explicit cluster provisioning.' >&2; exit 2; }
command -v pg_createcluster >/dev/null
[[ -x /usr/lib/postgresql/18/bin/postgres ]] || { echo 'Install official PostgreSQL 18 packages first.' >&2; exit 2; }
[[ ! -e /etc/postgresql/18/industrial_ai && ! -e /var/lib/postgresql/18/industrial_ai ]] || { echo 'Dedicated cluster path already exists; refusing to replace it.' >&2; exit 2; }
if ss -H -ltn 'sport = :5432' | read -r _; then echo 'Port 5432 is already in use; existing service is untouched.' >&2; exit 2; fi
pg_createcluster 18 industrial_ai --port 5432 --start-conf=manual -- --auth-local=peer --auth-host=scram-sha-256
install -o postgres -g postgres -m 0644 "$here/postgresql/private.conf" /etc/postgresql/18/industrial_ai/conf.d/industrial-ai.conf
install -o postgres -g postgres -m 0640 "$here/postgresql/pg_hba.conf" /etc/postgresql/18/industrial_ai/pg_hba.conf
printf 'Created dedicated PostgreSQL cluster with private listen address. It remains stopped; no database or roles created.\n'
