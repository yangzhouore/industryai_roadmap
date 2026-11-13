"""Timezone-aware daily slots and process-lifetime overlap protection."""
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo('Europe/Berlin')


def aware_now(now=None):
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('Scheduler time must include timezone')
    return value.astimezone(BERLIN)


def slot(day):
    return datetime.combine(date.fromisoformat(day), time(7), BERLIN)


def latest_due(now=None):
    local = aware_now(now)
    day = local.date() - timedelta(days=int(local.time() < time(7)))
    return day.isoformat()


def next_slot(now=None):
    local = aware_now(now)
    day = local.date() + timedelta(days=int(local.time() >= time(7)))
    return slot(day.isoformat()).astimezone(timezone.utc)


def missed_dates(start, completed=(), now=None):
    first, last = date.fromisoformat(start), date.fromisoformat(latest_due(now))
    done = set(completed)
    if (last - first).days > 3660:
        raise ValueError('Schedule audit range exceeds ten years')
    return [(first + timedelta(days=n)).isoformat()
            for n in range(max(0, (last-first).days + 1))
            if (first + timedelta(days=n)).isoformat() not in done]


class AlreadyRunning(RuntimeError):
    pass


@contextmanager
def run_lock(store, database):
    """PG session lock spans hosts; SQLite uses a crash-released OS file lock."""
    if store.postgres:
        locked = store.execute("SELECT pg_try_advisory_lock(hashtext(?))",
                               ('industrial-ai-daily-v1',)).fetchone()[0]
        if not locked:
            raise AlreadyRunning('Another daily pipeline owns the database lock')
        try:
            yield
        finally:
            store.execute("SELECT pg_advisory_unlock(hashtext(?))", ('industrial-ai-daily-v1',))
        return
    import os
    path = Path(str(database) + '.automation.lock').resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b'0'); handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise AlreadyRunning('Another daily pipeline owns the database lock') from None
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)
