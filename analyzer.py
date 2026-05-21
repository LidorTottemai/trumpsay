import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import anthropic

from config import settings
from fetcher import TrumpItem
from history import HistoryStore

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a financial market analyst specializing in political risk assessment.
Analyze Donald Trump's recent statements, actions, and news to predict their impact on US stock markets.

You must respond ONLY with valid JSON matching this exact schema:
{
  "market_direction": "UP" | "DOWN" | "NEUTRAL",
  "confidence_pct": <integer 0-100>,
  "key_driver": "<title or description of the most market-moving item>",
  "key_driver_url": "<url of the key driver>",
  "summary_he": "<2-3 sentences in Hebrew summarizing the analysis>",
  "sectors": [
    {
      "name": "<English sector name>",
      "direction": "UP" | "DOWN" | "NEUTRAL",
      "reasoning_he": "<one sentence in Hebrew explaining the impact>"
    }
  ]
}

Rules:
- sectors must contain EXACTLY 3 entries (different sectors)
- summary_he and reasoning_he MUST be written in Hebrew
- tariff threats → DOWN for import-heavy sectors (retail, tech hardware, auto)
- deregulation signals → UP for affected sectors (energy, finance)
- military/conflict rhetoric → UP for Defense, DOWN for international trade
- Fed/rate criticism → affects Financials and rate-sensitive REITs
- trade deal progress → UP for tech, industrials, agriculture
- If news is routine or non-market-moving → NEUTRAL with confidence 30-50
- Choose 3 DIFFERENT sectors that are most directly affected
- confidence_pct should reflect how clear and significant the signal is

Historical context rules:
- Use provided historical precedents as weighted evidence
- Similar past events with large market moves increase confidence
- Contradicting precedents lower confidence
"""

RETRY_SUFFIX = "\n\nYour previous response was not valid JSON. Please respond ONLY with valid JSON, no other text."


class Direction(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    NEUTRAL = "NEUTRAL"


@dataclass
class SectorPrediction:
    name: str
    direction: Direction
    reasoning_he: str


@dataclass
class MarketPrediction:
    market_direction: Direction
    confidence_pct: int
    key_driver: str
    key_driver_url: str
    summary_he: str
    sectors: list[SectorPrediction]
    generated_at: datetime
    source_count: int
    keywords: list[str] = field(default_factory=list)


def _build_user_prompt(items: list[TrumpItem], history: list[dict]) -> str:
    now = datetime.now(timezone.utc)

    from pytz import timezone as tz
    est = tz("America/New_York")
    now_est = datetime.now(est)

    market_open_est = now_est.replace(hour=9, minute=30, second=0, microsecond=0)
    minutes_until_open = int((market_open_est - now_est).total_seconds() / 60)
    if minutes_until_open < 0:
        minutes_until_open += 24 * 60

    day_names = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]
    day_he = day_names[now_est.weekday()]

    lines = [
        f"Today is {now_est.strftime('%A, %d.%m.%Y')} ({day_he}). "
        f"Market opens in {minutes_until_open} minutes.",
        "",
    ]

    if history:
        lines.append("HISTORICAL PRECEDENT (similar past events and actual market outcomes):")
        for i, ev in enumerate(history, 1):
            sp = ev.get("sp500_pct")
            sp_str = f"S&P 500 {'+' if sp >= 0 else ''}{sp:.2f}%" if sp is not None else "outcome unknown"
            lines.append(
                f"[{i}] {ev['date']} | Keywords: {ev['keywords']}\n"
                f"    Event: {ev['summary']}\n"
                f"    Actual result: {sp_str}"
            )
            if ev.get("notes"):
                lines.append(f"    Notes: {ev['notes']}")
        lines.append("")
        lines.append("Use this historical context as weighted evidence in your prediction.")
        lines.append("")

    source_names = sorted({item.source for item in items})
    lines.append(
        f"Trump's recent activity — last 18 hours "
        f"({len(items)} items from: {', '.join(source_names)}):"
    )
    lines.append("")

    for i, item in enumerate(items, 1):
        pub = item.published_at.strftime("%Y-%m-%d %H:%M EST")
        lines.append(f"[{i}] SOURCE: {item.source} | TIME: {pub}")
        if item.title:
            lines.append(f"TITLE: {item.title}")
        if item.content and item.content != item.title:
            snippet = item.content[:300]
            if len(item.content) > 300:
                snippet += "..."
            lines.append(f"CONTENT: {snippet}")
        if item.url:
            lines.append(f"URL: {item.url}")
        lines.append("---")

    lines.append("")
    lines.append("Provide your structured market prediction in JSON format.")
    return "\n".join(lines)


def _parse_response(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(text)


def _validate_and_build(data: dict, items: list[TrumpItem]) -> MarketPrediction:
    direction = Direction(data["market_direction"])
    confidence = max(0, min(100, int(data["confidence_pct"])))
    sectors = []
    for s in data["sectors"][:3]:
        sectors.append(SectorPrediction(
            name=s["name"],
            direction=Direction(s["direction"]),
            reasoning_he=s["reasoning_he"],
        ))

    key_url = data.get("key_driver_url", "")
    if not key_url and items:
        key_url = items[0].url

    return MarketPrediction(
        market_direction=direction,
        confidence_pct=confidence,
        key_driver=data.get("key_driver", ""),
        key_driver_url=key_url,
        summary_he=data["summary_he"],
        sectors=sectors,
        generated_at=datetime.now(timezone.utc),
        source_count=len(items),
    )


def analyze(items: list[TrumpItem], history_store: Optional[HistoryStore] = None) -> MarketPrediction:
    if not items:
        logger.warning("No items to analyze — returning NEUTRAL")
        return MarketPrediction(
            market_direction=Direction.NEUTRAL,
            confidence_pct=0,
            key_driver="אין נתונים",
            key_driver_url="",
            summary_he="לא נמצאו נתונים לניתוח היום.",
            sectors=[
                SectorPrediction("Technology", Direction.NEUTRAL, "אין מידע."),
                SectorPrediction("Energy", Direction.NEUTRAL, "אין מידע."),
                SectorPrediction("Financials", Direction.NEUTRAL, "אין מידע."),
            ],
            generated_at=datetime.now(timezone.utc),
            source_count=0,
        )

    keywords: list[str] = []
    historical: list[dict] = []
    if history_store:
        keywords = history_store.extract_keywords(items)
        historical = history_store.find_similar(keywords, limit=5)
        logger.info("Historical precedents found: %d", len(historical))

    user_prompt = _build_user_prompt(items, historical)

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    last_error: Exception = Exception("unknown")
    for attempt in range(3):
        prompt_suffix = RETRY_SUFFIX if attempt > 0 else ""
        try:
            response = client.messages.create(
                model=settings.claude_model,
                max_tokens=1024,
                system=[{
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[{
                    "role": "user",
                    "content": user_prompt + prompt_suffix,
                }],
            )
            text = next((b.text for b in response.content if b.type == "text"), "")
            logger.debug("Claude response (attempt %d): %s", attempt + 1, text[:200])

            data = _parse_response(text)
            prediction = _validate_and_build(data, items)
            prediction.keywords = keywords

            cache_hits = getattr(response.usage, "cache_read_input_tokens", 0) or 0
            logger.info(
                "Analysis complete: %s %d%% | cache_read=%d",
                prediction.market_direction, prediction.confidence_pct, cache_hits,
            )
            return prediction

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            last_error = e
            logger.warning("Parse error on attempt %d: %s", attempt + 1, e)
        except anthropic.APIError as e:
            last_error = e
            logger.error("Claude API error on attempt %d: %s", attempt + 1, e)
            break

    raise RuntimeError(f"Failed to get valid prediction after retries: {last_error}") from last_error
