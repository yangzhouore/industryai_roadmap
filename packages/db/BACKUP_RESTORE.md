# Encrypted backup and isolated recovery

## Safety contract
- Backups use standard pg_dump custom archives and age X25519 recipient encryption.
- A shared exported REPEATABLE READ READ ONLY snapshot binds table/review hashes to the dump.
- Clear dumps never touch disk; database passwords use temporary owner-only PGPASSFILE files.
- API keys and unrelated database URLs are removed from child environments and command arguments.
- PostgreSQL 18 clients are required for the existing 18.x database; match the server major version in CI.
- Install trusted pg_dump, pg_restore, age/age-keygen and rclone before configuring services.
- Source backups are read-only. No seed, migration, backfill, publication or source-table changes occur.

## Production backup configuration (activation requires approval)
Use a dedicated read-only database role with SELECT on all public application tables.
Provide DATABASE_URL in the protected backup service environment, not a shell argument.
BACKUP_AGE_RECIPIENT is a public age1... recipient; keep its private identity off the VPS.
RCLONE_CONFIG must explicitly name an owner-only configuration file for the backup OS user.
BACKUP_OFFHOST_APPROVED=true is an operator attestation that the destination is independent storage.
Only S3, B2, Azure Blob and Google Cloud Storage backends are accepted.
Local/alias/SFTP backends, TLS bypasses, environment endpoint overrides and private endpoints are rejected.
Other RCLONE_* overrides are rejected except the protected configuration file/passphrase settings.

```sh
python packages/db/recovery.py backup --database-env DATABASE_URL \
  --recipient-env BACKUP_AGE_RECIPIENT --destination rclone:offsite:industrial-ai \
  --state-dir /var/lib/industrial-ai/backups \
  --state-file /var/lib/industrial-ai/artifacts/mvp3/budget.json
```

The optional state file must be the existing budget ledger and is encrypted inside the manifest.
It preserves November carryover bytes/hash without exposing them in unencrypted files or logs.
Archive and manifest upload through temporary object names; downloaded ciphertext checksums are verified.
The encrypted manifest is published last as the complete-backup marker.
age authenticates ciphertext integrity, not sender identity; recover only from trusted backup custody.
Retain access-controlled audit logs and verify the storage account/location independently before activation.

## Retention
`prune --destination rclone:offsite:industrial-ai` produces a plan without deleting anything.
Only an explicit `--apply` expires recognized backup pairs outside seven daily dates/four ISO weeks.
Unknown files and incomplete uploads are not selected for deletion; inspect failures before pruning.
Do not prune until a successful restore and required retention have been independently verified.

## Isolated restore
Download the encrypted archive and matching encrypted manifest to a trusted recovery host.
Use an owner-only age identity file, and an empty NEW database named industrial_ai_restore_<unique>.
RESTORE_DATABASE_URL must name that target; it must not resolve to the source database.
The tool never creates, cleans, drops or overwrites an existing database or existing state file.
It rejects tables, functions, types, nonbaseline schemas/extensions, large objects and event triggers.

```sh
python packages/db/recovery.py restore --archive BACKUP.dump.age \
  --identity-file /private/restore-identity.txt --target-env RESTORE_DATABASE_URL \
  --expected-manifest BACKUP.manifest.json.age \
  --state-output /private/industrial_ai_restore_UNIQUE/budget.json
```

The target database must use lowercase letters/numbers/underscores after the required prefix.
Replace UNIQUE in the path with the exact target database name suffix.
Optional budget output is allowed only under a directory named exactly after that isolated database.
All public-table hashes, real-article counts, bilingual issue hashes and revision/review hashes must match.
Hashes normalize the connection timezone to UTC, so host timezone differences do not change them.
Only after acceptance and separate authorization should a production target be prepared and cut over.

## Verification performed for MVP-4.1
- Real pg_dump 18.7 -> age 1.3.2 -> encrypted custody simulation -> pg_restore succeeded locally.
- A new isolated target restored 140 real articles, November 6/9/13 bilingual editions and one revision.
- November 17 rerun: all 19 public-table hashes matched; original source records remained unchanged.
- All 15 recovery tests passed, including corrupted archive refusal, read-only snapshots and malformed-DSN redaction.
- Test identity/ciphertexts are ignored private artifacts; no private key or plaintext dump was committed.
- The custody test used an explicitly test-only local transport, not a genuine external upload.
- Actual remote storage credentials, off-host transfer, restore custody and alert delivery remain deployment gates.
- Opt-in CI tests create/drop only their newly allocated UUID test databases and use no OpenAI keys.

```sh
RUN_RECOVERY_INTEGRATION=1 python -m unittest packages.db.test_recovery -v
```

Use TEST_RECOVERY_ADMIN_URL or TEST_DATABASE_URL for a dedicated disposable cluster/database.
The test refuses the existing digest database as its admin target and requires actual backup/encryption tools.
