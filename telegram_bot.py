import logging
from datetime import datetime

import requests

from analyzer import Direction, MarketPrediction
from config import settings

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

DIRECTION_EMOJI = {
    Direction.UP: "🟢",
    Direction.DOWN: "🔴",
    Direction.NEUTRAL: "🟡",
}

DIRECTION_HE = {
    Direction.UP: "עלייה",
    Direction.DOWN: "ירידה",
    Direction.NEUTRAL: "ניטרלי",
}

CONFIDENCE_PHRASE = {
    Direction.UP: "הבוט בטוח ב־{pct}% שהשוק יגיב בחיוב",
    Direction.DOWN: "הבוט בטוח ב־{pct}% שהשוק יגיב בשלילה",
    Direction.NEUTRAL: "הבוט בטוח ב־{pct}% שהשוק לא יגיב באופן חד",
}

DAY_NAMES_HE = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]


def _confidence_bar(pct: int) -> str:
    filled = min(5, round(pct / 20))
    return "▓" * filled + "░" * (5 - filled)


def _format_message(pred: MarketPrediction) -> str:
    from pytz import timezone as tz
    from datetime import timezone as dt_tz, timedelta
    il_tz = tz.timezone("Asia/Jerusalem")
    now_il = datetime.now(il_tz)
    day_he = DAY_NAMES_HE[now_il.weekday()]
    date_str = now_il.strftime("%d.%m.%Y")

    dir_emoji = DIRECTION_EMOJI[pred.market_direction]
    dir_he = DIRECTION_HE[pred.market_direction]
    conf_phrase = CONFIDENCE_PHRASE[pred.market_direction].format(pct=pred.confidence_pct)
    conf_bar = _confidence_bar(pred.confidence_pct)

    # Calculate minutes until NYSE open (9:30 AM ET) from now
    et_tz = tz.timezone("America/New_York")
    now_et = datetime.now(et_tz)
    market_open_et = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    minutes_until = int((market_open_et - now_et).total_seconds() / 60)
    if minutes_until < 0:
        minutes_until += 24 * 60

    sectors_text = ""
    for sector in pred.sectors[:3]:
        s_emoji = DIRECTION_EMOJI[sector.direction]
        s_he = DIRECTION_HE[sector.direction]
        sectors_text += (
            f"{s_emoji} *{sector.name}* — {s_he}\n"
            f"  └ {sector.reasoning_he}\n"
        )

    source_url = pred.key_driver_url or "https://truthsocial.com/@realDonaldTrump"

    lines = [
        f"📊 *תחזית שוק יומית* | יום {day_he}, {date_str}",
        "━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"{dir_emoji} *תחזית: {dir_he}*",
        f"🎯 *{conf_phrase}* {conf_bar}",
        "",
        "📰 *האירוע המניע:*",
        f"_{pred.key_driver}_",
        "",
        "🔍 *ניתוח:*",
        pred.summary_he,
        "",
        "📊 *סקטורים מושפעים:*",
        sectors_text.rstrip(),
        "",
        f"🕐 _שוק נפתח בעוד {minutes_until} דקות_",
        f"🔗 [מקור]({source_url})",
        "",
        "_⚠️ לצורך מידע בלבד. אינה המלצת השקעה._",
    ]
    return "\n".join(lines)


def send_prediction(pred: MarketPrediction) -> bool:
    if settings.dry_run:
        print("\n" + "=" * 60)
        print(_format_message(pred))
        print("=" * 60 + "\n")
        return True

    text = _format_message(pred)
    url = TELEGRAM_API.format(token=settings.telegram_bot_token)
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False,
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 401:
            logger.critical("Telegram bot token is invalid — check TELEGRAM_BOT_TOKEN in .env")
            return False
        if resp.status_code == 403:
            logger.critical("Telegram bot cannot send to chat — check TELEGRAM_CHAT_ID or add bot as channel admin")
            return False
        if resp.status_code == 429:
            logger.warning("Telegram rate limit hit — message not sent")
            return False
        resp.raise_for_status()
        logger.info("Telegram message sent successfully")
        return True
    except requests.RequestException as e:
        logger.error("Failed to send Telegram message: %s", e)
        return False


def send_error(message_he: str) -> None:
    if settings.dry_run:
        print(f"\n[ERROR] {message_he}\n")
        return

    text = f"⚠️ *שגיאה בתחזית*\n\n{message_he}"
    url = TELEGRAM_API.format(token=settings.telegram_bot_token)
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 401:
            logger.critical("Telegram bot token is invalid — check TELEGRAM_BOT_TOKEN in .env")
            return
        if resp.status_code == 403:
            logger.critical("Telegram bot cannot send to chat — check TELEGRAM_CHAT_ID or add bot as channel admin")
            return
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error("Failed to send error message to Telegram: %s", e)
