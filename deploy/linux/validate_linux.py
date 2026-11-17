"""Validate Linux units/calendar/Caddy without installing or starting any service."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-caddy', action='store_true')
    args = parser.parse_args()
    for shell in HERE.glob('*.sh'):
        subprocess.run(['bash', '-n', str(shell)], check=True)
    subprocess.run(['systemd-analyze', 'calendar', '--iterations=3', '*-*-* 07:00:00 Europe/Berlin'], check=True)
    # A synthetic root makes target-only executable/dependency paths available to
    # the parser. Nothing in this temporary root can start a service or database.
    with tempfile.TemporaryDirectory(prefix='industrial-ai-systemd-') as folder:
        root = Path(folder)
        units = root/'etc/systemd/system'
        units.mkdir(parents=True)
        for source in (HERE/'systemd').glob('*.service'):
            shutil.copyfile(source, units/source.name)
        for source in (HERE/'systemd').glob('*.timer'):
            shutil.copyfile(source, units/source.name)
        for target in ('sysinit.target', 'basic.target', 'shutdown.target', 'timers.target',
                       'multi-user.target', 'network-online.target'):
            (units/target).write_text('[Unit]\nDescription=Validation dependency\n')
        (units/'postgresql@18-industrial_ai.service').write_text('[Service]\nType=oneshot\nExecStart=/usr/bin/true\n')
        for executable in ('usr/bin/node', 'usr/bin/true', 'srv/industrial-ai/venv/bin/python'):
            path = root/executable
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('#!/bin/sh\nexit 0\n'); path.chmod(0o755)
        subprocess.run(['systemd-analyze', '--root='+str(root), 'verify', '--man=no',
                        *[str(path) for path in units.glob('industrial-ai-*')]], check=True)
    if not args.skip_caddy:
        env = dict(os.environ, SITE_HOST='validation.example.com', ACME_EMAIL='validation@example.invalid')
        with tempfile.TemporaryDirectory(prefix='industrial-ai-caddy-') as folder:
            # The validation-only log directory avoids requiring root /var/log access.
            config = Path(folder)/'Caddyfile'
            config.write_text((HERE/'Caddyfile').read_text().replace('/var/log/industrial-ai', folder))
            subprocess.run(['caddy', 'validate', '--config', str(config), '--adapter', 'caddyfile'], env=env, check=True)
    print('Linux configuration parsers passed; no units installed, started or enabled.')


if __name__ == '__main__':
    main()
