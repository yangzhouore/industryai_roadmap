"""Fail-closed environment checks; never prints credentials or changes services."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

ROLES = {'web': 'industrial_web', 'worker': 'industrial_worker',
         'migration': 'industrial_owner', 'backup': 'industrial_backup', 'health': 'industrial_web'}
UNSAFE = {'digest', 'postgres', 'password', 'changeme', 'example', 'replace-me'}


def domain(value):
    if (not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?', value)
            or '.' not in value or value.endswith(('.invalid', '.localhost', '.local'))
            or value in {'localhost', 'example.com', 'example.org', 'example.net'}):
        raise ValueError('Configure a real approved public hostname')
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return value
    raise ValueError('Use the approved DNS hostname, not an IP address')


def database(value, role):
    try:
        parsed = urlsplit(value)
        password = unquote(parsed.password or '')
        if (parsed.scheme not in {'postgres', 'postgresql'} or parsed.hostname not in {'127.0.0.1', 'localhost'}
                or parsed.port not in (None, 5432) or parsed.path != '/industrial_ai'
                or parsed.query or parsed.fragment
                or parsed.username != ROLES[role] or len(password) < 24
                or password.casefold() in UNSAFE):
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Configure a private industrial_ai connection with the assigned role and strong credential') from None


def check(role, env=None, root=None):
    env = os.environ if env is None else env
    root = Path(root or Path(__file__).resolve().parents[2])
    if role in ROLES:
        database(env.get('DATABASE_URL'), role)
    if role == 'web':
        site = urlsplit(env.get('SITE_URL', ''))
        if (site.scheme != 'https' or site.path not in ('', '/') or site.query or site.fragment
                or site.username or site.password or site.port not in (None, 443)):
            raise ValueError('SITE_URL must be the approved HTTPS origin at build and runtime')
        domain(site.hostname)
        if env.get('DATA_MODE') != 'database' or env.get('OPENAI_API_KEY'):
            raise ValueError('Web reader requires database mode and must receive no OpenAI key')
    if role == 'worker':
        cfg = json.loads((root/'config/automation.json').read_text(encoding='utf-8'))
        if cfg.get('timezone') != 'Europe/Berlin' or cfg.get('publicationTime') != '07:00':
            raise ValueError('Unexpected daily schedule configuration')
        if env.get('UNATTENDED_PAID_APPROVED') not in (None, '', 'false', 'true'):
            raise ValueError('Invalid unattended paid approval flag')
    if role == 'backup' and env.get('BACKUP_OFFHOST_APPROVED') != 'true':
        raise ValueError('Off-host destination approval is required before any backup upload')
    if role == 'proxy':
        domain(env.get('SITE_HOST'))
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', env.get('ACME_EMAIL', '')):
            raise ValueError('Configure the operator ACME contact email')
    return {'component': role, 'configuration': 'valid', 'credentials': 'withheld'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('component', choices=[*ROLES, 'proxy'])
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.component)))
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as error:
        print(json.dumps({'component': args.component, 'configuration': 'invalid', 'reason': str(error)}))
        raise SystemExit(1)
