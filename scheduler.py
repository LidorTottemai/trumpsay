import logging
from datetime import date, timedelta

import pytz
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config import settings

logger = logging.getLogger(__name__)


def _easter(year: int) -> date:
    """Computus algorithm for Easter Sunday (Gregorian)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(114 + h + l - 7 * m, 31)
    return date(year, month, day + 1)


def _observed(d: date) -> date:
    """Return observed date: Sat→Fri, Sun→Mon."""
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """Return the nth occurrence (1-based) of weekday (0=Mon) in month/year."""
    first = date(year, month, 1)
    delta = (weekday - first.weekday()) % 7
    return first + timedelta(days=delta + (n - 1) * 7)


def _last_monday(year: int, month: int) -> date:
    """Last Monday of the given month."""
    # Start from end of month
    if month == 12:
        last = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    return last - timedelta(days=(last.weekday()) % 7)


def _nyse_holidays(year: int) -> set[date]:
    easter = _easter(year)
    return {
        _observed(date(year, 1, 1)),                         # New Year's Day
        _nth_weekday(year, 1, 0, 3),                        # MLK Day (3rd Mon Jan)
        _nth_weekday(year, 2, 0, 3),                        # Presidents' Day (3rd Mon Feb)
        easter - timedelta(days=2),                          # Good Friday
        _last_monday(year, 5),                               # Memorial Day (last Mon May)
        _observed(date(year, 6, 19)),                        # Juneteenth
        _observed(date(year, 7, 4)),                         # Independence Day
        _nth_weekday(year, 9, 0, 1),                        # Labor Day (1st Mon Sep)
        _nth_weekday(year, 11, 3, 4),                       # Thanksgiving (4th Thu Nov)
        _observed(date(year, 12, 25)),                       # Christmas
    }


def _is_market_day() -> bool:
    """Return True if today (New York time) is an NYSE trading day."""
    et_tz = pytz.timezone("America/New_York")
    from datetime import datetime
    today = datetime.now(et_tz).date()
    if today.weekday() >= 5:  # Saturday or Sunday
        return False
    if today in _nyse_holidays(today.year):
        return False
    return True


def run_pipeline() -> None:
    from fetcher import fetch_all
    from analyzer import analyze
    from telegram_bot import send_prediction, send_error
    from history import HistoryStore

    if not _is_market_day():
        logger.info("Today is not an NYSE trading day — skipping pipeline")
        return

    logger.info("Starting daily pipeline run")
    history_store = HistoryStore(settings.db_path)

    try:
        items = fetch_all(newsapi_key=settings.newsapi_key)
        if not items:
            logger.warning("No items fetched — sending error notification")
            send_error("לא נמצאו נתונים לניתוח היום. בדוק את חיבור הרשת.")
            return

        logger.info("Fetched %d items, running analysis", len(items))
        prediction = analyze(items, history_store=history_store)

        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        history_store.record_prediction(
            date=today,
            summary=prediction.key_driver,
            keywords=prediction.keywords,
        )

        sent = send_prediction(prediction)
        if not sent:
            logger.error("Failed to send Telegram message")

    except Exception as e:
        logger.critical("Pipeline failed: %s", e, exc_info=True)
        send_error(f"שגיאה קריטית בצינור הנתונים: {str(e)[:200]}")


def start_scheduler() -> None:
    tz = pytz.timezone(settings.timezone)

    logger.info(
        "Starting scheduler: will run daily at %02d:%02d %s",
        settings.send_hour, settings.send_minute, settings.timezone,
    )

    scheduler = BlockingScheduler(timezone=tz)
    scheduler.add_job(
        run_pipeline,
        trigger=CronTrigger(
            hour=settings.send_hour,
            minute=settings.send_minute,
            timezone=tz,
        ),
        misfire_grace_time=300,
        id="daily_prediction",
        name="Daily Trump Market Prediction",
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")
