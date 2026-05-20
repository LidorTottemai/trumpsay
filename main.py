#!/usr/bin/env python3
import argparse
import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def cmd_run(args) -> None:
    from config import settings
    setup_logging(settings.log_level)
    from scheduler import start_scheduler
    start_scheduler()


def cmd_once(args) -> None:
    from config import settings
    if args.dry_run:
        settings.dry_run = True
    setup_logging(settings.log_level)
    from scheduler import run_pipeline
    run_pipeline()


def cmd_test_fetch(args) -> None:
    setup_logging("INFO")
    from config import settings
    from fetcher import fetch_all
    items = fetch_all(newsapi_key=settings.newsapi_key)
    print(f"\nFetched {len(items)} items:\n")
    for i, item in enumerate(items, 1):
        print(f"[{i}] {item.source.upper()} | {item.published_at.strftime('%Y-%m-%d %H:%M')}")
        print(f"    {item.title[:100]}")
        if item.url:
            print(f"    {item.url}")
        print()


def cmd_test_telegram(args) -> None:
    setup_logging("INFO")
    from analyzer import Direction, MarketPrediction, SectorPrediction
    from telegram_bot import send_prediction
    from datetime import datetime, timezone

    pred = MarketPrediction(
        market_direction=Direction.UP,
        confidence_pct=75,
        key_driver="Test message — bot is working",
        key_driver_url="https://truthsocial.com/@realDonaldTrump",
        summary_he="זו הודעת בדיקה לוודא שהבוט עובד כראוי. הניתוח האמיתי יישלח בכל בוקר לפני פתיחת השוק.",
        sectors=[
            SectorPrediction("Technology", Direction.UP, "בדיקת תקשורת עם הערוץ."),
            SectorPrediction("Energy", Direction.NEUTRAL, "הודעת בדיקה בלבד."),
            SectorPrediction("Financials", Direction.UP, "המערכת פועלת תקין."),
        ],
        generated_at=datetime.now(timezone.utc),
        source_count=0,
    )
    success = send_prediction(pred)
    sys.exit(0 if success else 1)


def cmd_record_outcome(args) -> None:
    setup_logging("INFO")
    from config import settings
    from history import HistoryStore

    store = HistoryStore(settings.db_path)
    import sqlite3
    with sqlite3.connect(settings.db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, date, summary FROM events WHERE date = ? AND sp500_pct IS NULL",
            (args.date,),
        ).fetchall()

    if not rows:
        print(f"No pending prediction found for {args.date}.")
        sys.exit(1)

    if len(rows) > 1:
        print("Multiple predictions found:")
        for row in rows:
            print(f"  [{row['id']}] {row['summary'][:80]}")
        print("Use --event-id to specify which one.")
        sys.exit(1)

    event_id = args.event_id or rows[0]["id"]
    store.record_outcome(event_id, args.sp500)
    print(f"Recorded: event {event_id} on {args.date} → S&P {'+' if args.sp500 >= 0 else ''}{args.sp500:.2f}%")


def main() -> None:
    parser = argparse.ArgumentParser(description="Trump Market Predictor")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("run", help="Start the daily scheduler")

    once_p = sub.add_parser("once", help="Run pipeline once immediately")
    once_p.add_argument("--dry-run", action="store_true", help="Print instead of sending to Telegram")

    sub.add_parser("test-fetch", help="Fetch items and print them (no Claude call)")
    sub.add_parser("test-telegram", help="Send a test message to Telegram")

    outcome_p = sub.add_parser("record-outcome", help="Record actual S&P 500 outcome")
    outcome_p.add_argument("--date", required=True, help="Date (YYYY-MM-DD)")
    outcome_p.add_argument("--sp500", required=True, type=float, help="S&P 500 % change (e.g. +1.4 or -2.1)")
    outcome_p.add_argument("--event-id", type=int, help="Specific event ID (if multiple for the date)")

    args = parser.parse_args()

    dispatch = {
        "run": cmd_run,
        "once": cmd_once,
        "test-fetch": cmd_test_fetch,
        "test-telegram": cmd_test_telegram,
        "record-outcome": cmd_record_outcome,
    }

    if not args.command:
        parser.print_help()
        sys.exit(1)

    dispatch[args.command](args)


if __name__ == "__main__":
    main()
