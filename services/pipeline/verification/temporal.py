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


def daily_source_window(issue_date):
    """Previous complete Berlin calendar day, independent of DST day length."""
    # day_bounds also enforces a canonical YYYY-MM-DD edition date.
    day_bounds(issue_date)
    source_date = (date.fromisoformat(issue_date) - timedelta(days=1)).isoformat()
    start, end = day_bounds(source_date)
    return {"dateBasis": "previous_complete_berlin_day", "sourceDate": source_date,
            "startInclusive": start.isoformat(), "endExclusive": end.isoformat(),
            "timezone": "Europe/Berlin"}


def in_daily_source_window(timestamp, issue_date):
    window = daily_source_window(issue_date)
    return (publication_time(window["startInclusive"]) <= publication_time(timestamp)
            < publication_time(window["endExclusive"]))
