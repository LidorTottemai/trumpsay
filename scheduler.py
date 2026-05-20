import logging

import pytz
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config import settings

logger = logging.getLogger(__name__)


def run_pipeline() -> None:
    from fetcher import fetch_all
    from analyzer import analyze
    from telegram_bot import send_prediction, send_error
    from history import HistoryStore

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
    hour = settings.market_open_hour
    offset = settings.send_offset_minutes

    send_hour = hour
    send_minute = -offset
    if send_minute < 0:
        send_hour -= 1
        send_minute += 60

    logger.info(
        "Starting scheduler: will run daily at %02d:%02d %s",
        send_hour, send_minute, settings.timezone,
    )

    scheduler = BlockingScheduler(timezone=tz)
    scheduler.add_job(
        run_pipeline,
        trigger=CronTrigger(
            hour=send_hour,
            minute=send_minute,
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
