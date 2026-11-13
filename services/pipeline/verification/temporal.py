"""Berlin editorial-day boundaries, including DST transitions."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")


def day_bounds(issue_date):
    day = date.fromisoformat(issue_date)
    if day.isoformat() != issue_date:
        raise ValueError("Issue date must be YYYY-MM-DD")
    start = datetime.combine(day, time.min, BERLIN)
    end = datetime.combine(day + timedelta(days=1), time.min, BERLIN)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def publication_time(timestamp):
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Publication timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def publication_day(timestamp):
    return publication_time(timestamp).astimezone(BERLIN).date().isoformat()
