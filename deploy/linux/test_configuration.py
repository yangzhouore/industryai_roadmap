"""Offline production guard tests. Never provisions, connects or enables units."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('production_preflight', HERE/'preflight.py')
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


class ProductionConfigurationTests(unittest.TestCase):
    def test_example_files_cannot_pass_real_production_preflight(self):
        for role in ('web', 'worker', 'migration', 'backup', 'health', 'proxy'):
            env = dict(line.split('=', 1) for line in (HERE/'environment'/f'{role}.env.example').read_text().splitlines() if '=' in line)
            with self.subTest(role=role), self.assertRaises(ValueError):
                preflight.check(role, env)

    def test_web_accepts_only_scoped_private_reader_without_ai_secret(self):
        env = {'DATABASE_URL': 'postgresql://industrial_web:'+('x'*30)+'@127.0.0.1:5432/industrial_ai',
               'DATA_MODE': 'database', 'SITE_URL': 'https://digest.company.co.uk'}
        self.assertEqual(preflight.check('web', env)['configuration'], 'valid')
        for field, value in [('DATABASE_URL', env['DATABASE_URL'].replace('industrial_web', 'industrial_worker')),
                             ('DATABASE_URL', env['DATABASE_URL'].replace('127.0.0.1', '203.0.113.10')),
                             ('DATA_MODE', 'fixture'), ('SITE_URL', 'https://user:password@digest.company.co.uk'),
                             ('OPENAI_API_KEY', 'unit-only-sentinel')]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                preflight.check('web', dict(env, **{field: value}))

    def test_database_uri_cannot_override_private_host_or_role(self):
        connection = 'postgresql://industrial_web:'+('x'*30)+'@127.0.0.1:5432/industrial_ai'
        for suffix in ('?host=203.0.113.10', '?hostaddr=203.0.113.10',
                       '?user=industrial_owner', '?dbname=other', '?options=-c%20search_path=other',
                       '#unexpected'):
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                preflight.database(connection+suffix, 'web')

    def test_proxy_requires_real_dns_name_and_operator_email(self):
        self.assertEqual(preflight.check('proxy', {'SITE_HOST': 'digest.company.co.uk', 'ACME_EMAIL': 'ops@company.co.uk'})['configuration'], 'valid')
        for host in ('example.invalid', 'example.com', '127.0.0.1', 'localhost', 'host;command'):
            with self.subTest(host=host), self.assertRaises(ValueError):
                preflight.check('proxy', {'SITE_HOST': host, 'ACME_EMAIL': 'ops@company.co.uk'})

    def test_worker_and_timer_default_to_dry_run_without_enable_action(self):
        service = (HERE/'systemd/industrial-ai-pipeline.service').read_text()
        self.assertIn('tick --dry-run --resume', service)
        self.assertNotIn('--allow-paid', service)
        self.assertIn('TimeoutStartSec=30min', service)
        timer = (HERE/'systemd/industrial-ai-pipeline.timer').read_text()
        self.assertIn('OnCalendar=*-*-* 07:00:00 Europe/Berlin', timer)
        self.assertIn('OnCalendar=*-*-* 09:15:00 Europe/Berlin', timer)
        self.assertIn('Persistent=true', timer)
        bootstrap = (HERE/'bootstrap.sh').read_text()
        for action in ('systemctl enable', 'systemctl start', 'systemctl restart'):
            self.assertNotIn(action, bootstrap)

    def test_private_postgres_and_distinct_readonly_secret_scopes(self):
        cfg = (HERE/'postgresql/private.conf').read_text()
        self.assertIn("listen_addresses = '127.0.0.1'", cfg)
        self.assertNotIn("listen_addresses = '*'", cfg)
        hba = (HERE/'postgresql/pg_hba.conf').read_text()
        self.assertIn('0.0.0.0/0', hba)
        self.assertIn('reject', hba)
        self.assertNotIn('OPENAI_API_KEY', (HERE/'environment/web.env.example').read_text())
        health = (HERE/'systemd/industrial-ai-health.service').read_text()
        self.assertIn('User=industrial-worker', health)
        self.assertIn('health.env', health)
        self.assertIn('SupplementaryGroups=industrial-ai', (HERE/'systemd/caddy.service.d/industrial-ai.conf').read_text())

    def test_database_tools_are_noop_without_explicit_mutation_flags(self):
        for script in ('provision_database.py', 'grant_database.py', 'prepare_release.py'):
            completed = subprocess.run([sys.executable, str(HERE/script)], capture_output=True, text=True, check=False)
            self.assertEqual(completed.returncode, 0)
            self.assertTrue('Dry check only' in completed.stdout or 'Read-only check' in completed.stdout)

    def test_backup_service_requires_offhost_approval_and_has_distinct_state(self):
        env = {'DATABASE_URL': 'postgresql://industrial_backup:'+('x'*30)+'@127.0.0.1:5432/industrial_ai'}
        with self.assertRaises(ValueError):
            preflight.check('backup', env)
        self.assertEqual(preflight.check('backup', dict(env, BACKUP_OFFHOST_APPROVED='true'))['configuration'], 'valid')
        unit = (HERE/'systemd/industrial-ai-backup.service').read_text()
        self.assertIn('User=industrial-backup', unit)
        self.assertIn('ReadWritePaths=/var/lib/industrial-ai/backups', unit)
        self.assertNotIn('worker.env', unit)
        self.assertIn('OnCalendar=*-*-* 03:30:00 Europe/Berlin', (HERE/'systemd/industrial-ai-backup.timer').read_text())

    def test_release_preparation_creates_cache_but_does_not_promote_or_start(self):
        source = (HERE/'prepare_release.py').read_text()
        self.assertIn("cache.mkdir(parents=True, exist_ok=True)", source)
        self.assertIn('own_tree(cache, reader.pw_uid, reader.pw_gid)', source)
        self.assertNotIn('systemctl', source)
        self.assertNotIn("'/srv/industrial-ai/current').symlink_to", source)
        import prepare_release
        env = prepare_release.build_environment({'SITE_URL':'https://digest.company.co.uk',
            'DATABASE_URL':'private-database-sentinel', 'OPENAI_API_KEY':'private-key-sentinel'})
        self.assertEqual(env['SITE_URL'], 'https://digest.company.co.uk')
        self.assertNotIn('DATABASE_URL', env)
        self.assertNotIn('OPENAI_API_KEY', env)
        self.assertIn("git+['ls-files','--others','-z']", source)
        self.assertIn("name.startswith('.env') and not name.endswith('.example')", source)
        self.assertIn('Never rebuild or change permissions on the currently selected release', source)

    def test_explicit_database_mutation_guard_runs_in_same_session_before_changes(self):
        import dedicated_cluster
        self.assertIn("current_setting('config_file')", dedicated_cluster.GUARD)
        self.assertIn("current_setting('data_directory')", dedicated_cluster.GUARD)
        self.assertIn('/etc/postgresql/18/industrial_ai/postgresql.conf', dedicated_cluster.GUARD)
        self.assertIn('/var/lib/postgresql/18/industrial_ai', dedicated_cluster.GUARD)
        self.assertIn('--username=postgres', dedicated_cluster.psql_command())
        import grant_database
        from unittest.mock import patch
        with patch.object(grant_database.os, 'name', 'posix'), patch.object(grant_database.os, 'geteuid', return_value=0, create=True), \
             patch.object(grant_database.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1)) as run:
            with self.assertRaises(ValueError):
                grant_database.main(['--apply'])
        script = run.call_args.kwargs['input']
        self.assertTrue(script.startswith(dedicated_cluster.GUARD))
        self.assertLess(script.index('current_setting'), script.index('GRANT'))


if __name__ == '__main__':
    unittest.main()
