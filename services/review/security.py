"""Local filesystem and exact shared-gate boundaries; no network or provider requests."""
import json
import os
from pathlib import Path
import stat
import subprocess
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
MAX_JSON = 8 * 1024 * 1024
MAX_EVIDENCE = 2 * 1024 * 1024


class ReviewError(RuntimeError):
    pass


def plain_json(value):
    try:
        return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (ValueError, TypeError, RecursionError):
        raise ReviewError('Invalid bounded JSON document') from None


def no_links(path):
    path = Path(os.path.abspath(path))
    for current in [*reversed(path.parents), path]:
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 1024:
            raise ReviewError('Symlinks and reparse points are not permitted')
    return path


def private_access(path):
    path = no_links(path)
    if os.name == 'nt':
        from packages.db.recovery import require_private_identity
        try:
            require_private_identity(path)
        except Exception:
            raise ReviewError('Private owner-only filesystem access is required') from None
    elif path.stat().st_uid != os.getuid() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ReviewError('Private owner-only filesystem access is required')
    return path


def private_root(path):
    path = no_links(path)
    if any(part.lower() in {'public', 'static', 'www', 'wwwroot', 'htdocs', '.git', '.next', 'node_modules'} for part in path.parts):
        raise ReviewError('Review state must not be placed in a served or source-control directory')
    try:
        local = path.relative_to(ROOT)
    except ValueError:
        pass
    else:
        if len(local.parts) < 2 or local.parts[0] != 'artifacts':
            raise ReviewError('Repository-local private state must be under ignored artifacts only')
    try:
        path.relative_to(ROOT/'apps'/'web')
    except ValueError:
        pass
    else:
        raise ReviewError('Review state must stay outside the website')
    if not path.exists():
        path.mkdir(mode=0o700, parents=True)
        if os.name == 'nt':
            from packages.db.recovery import protect_windows_directory
            protect_windows_directory(path)
    if not path.is_dir():
        raise ReviewError('Private state must be a directory')
    return private_access(path)


def read_private(path, limit=MAX_JSON):
    path = private_access(path)
    if not path.is_file() or path.stat().st_size > limit:
        raise ReviewError('Private input file is missing or exceeds its bound')
    with path.open('rb') as stream:
        data = stream.read(limit+1)
    if len(data) > limit:
        raise ReviewError('Input exceeds its bound')
    return data


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def load_private_json(path):
    try:
        value = json.loads(read_private(path).decode('utf-8-sig'), object_pairs_hook=unique_pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        plain_json(value)
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise ReviewError('Invalid private JSON input') from None


def new_file(path, data):
    path = no_links(path)
    if not path.parent.is_dir() or path.exists():
        raise ReviewError('Output must be new in an existing private directory')
    private_access(path.parent)
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return path


def https_reference(value):
    if not isinstance(value, str) or not value or len(value) > 2048:
        raise ReviewError('Documented HTTPS reference required')
    try:
        url = urlsplit(value)
        if url.scheme != 'https' or not url.hostname or url.username or url.password or any(c.isspace() for c in value):
            raise ValueError()
    except ValueError:
        raise ReviewError('Documented HTTPS reference required') from None
    return value


def bilingual(value):
    if not isinstance(value, dict) or set(value) != {'en', 'zh'} or any(not isinstance(v, str) or not v.strip() or len(v) > 20000 for v in value.values()):
        raise ReviewError('Nonempty documented EN/ZH reasons are required')
    return {'en': value['en'], 'zh': value['zh']}


def bridge(action, issue, policy=None):
    message = {'action': action, 'issue': issue}
    if policy is not None:
        message['policy'] = policy
    body = plain_json(message).encode('utf-8')
    if len(body) > MAX_JSON:
        raise ReviewError('Shared gate request exceeds its bound')
    # Do not forward database/API credentials to the offline Node bridge.
    env = {key: value for key, value in os.environ.items() if key.upper() in {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'HOME', 'USERPROFILE'}}
    try:
        result = subprocess.run(['node', str(ROOT/'packages/shared/public-display-cli.cjs')], input=body,
                                capture_output=True, timeout=30, env=env, check=False)
        if result.returncode or len(result.stdout) > MAX_JSON:
            raise ValueError()
        return json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        raise ReviewError('Shared public gate refused or is unavailable; details withheld') from None
