"""Fixed target identity guard for explicit local PostgreSQL provisioning."""
GUARD = '''DO $industrial_cluster_guard$
BEGIN
 IF current_setting('config_file') <> '/etc/postgresql/18/industrial_ai/postgresql.conf'
    OR current_setting('data_directory') <> '/var/lib/postgresql/18/industrial_ai' THEN
  RAISE EXCEPTION 'Refusing to modify a different PostgreSQL cluster';
 END IF;
END
$industrial_cluster_guard$;
'''


def psql_command():
    return ['runuser','-u','postgres','--','psql','--no-psqlrc','--quiet','--set=ON_ERROR_STOP=1',
            '--username=postgres','--host=/var/run/postgresql','--port=5432','--dbname=postgres']
