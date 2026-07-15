from datetime import datetime, timedelta, timezone


PROJECT_TIMEZONE = timezone(timedelta(hours=8), "UTC+08:00")


def utc_now() -> datetime:
    return datetime.now(PROJECT_TIMEZONE)
