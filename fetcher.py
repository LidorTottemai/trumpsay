import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher

import feedparser
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

TRUMP_KEYWORDS = {
    "trump", "tariff", "tariffs", "trade war", "federal reserve", "executive order",
    "white house", "sanctions", "mar-a-lago", "maga", "truth social", "trade deal",
    "china", "ukraine", "nato", "fed rate", "powell", "sec", "doge", "elon",
}

NEWS_FEEDS = [
    ("reuters", "https://feeds.reuters.com/reuters/topNews"),
    ("ap", "https://feeds.apnews.com/rss/apf-topnews"),
    ("fox", "https://moxie.foxnews.com/google-publisher/politics.xml"),
    ("politico", "https://www.politico.com/rss/politicopicks.xml"),
    ("bloomberg", "https://feeds.bloomberg.com/markets/news.rss"),
]

TRUTH_SOCIAL_RSS = "https://rss.truthsocial.com/@realDonaldTrump"
CNN_TRUTH_ARCHIVE = "https://ix.cnn.io/data/truth-social/truth_archive.json"
WHITEHOUSE_URL = "https://www.whitehouse.gov/briefing-room/presidential-actions/"
NEWSAPI_URL = "https://newsapi.org/v2/everything"


@dataclass
class TrumpItem:
    source: str
    published_at: datetime
    title: str
    content: str
    url: str

    @property
    def raw_text(self) -> str:
        return f"{self.title}. {self.content}".strip()


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _is_trump_related(item: TrumpItem) -> bool:
    combined = (item.title + " " + item.content).lower()
    return any(kw in combined for kw in TRUMP_KEYWORDS)


def _cutoff(hours: int = 18) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=hours)


def _dedup(items: list[TrumpItem]) -> list[TrumpItem]:
    unique: list[TrumpItem] = []
    for candidate in items:
        for existing in unique:
            ratio = SequenceMatcher(None, candidate.raw_text[:200], existing.raw_text[:200]).ratio()
            if ratio > 0.8:
                break
        else:
            unique.append(candidate)
    return unique


def _fetch_truth_social_rss() -> list[TrumpItem]:
    try:
        feed = feedparser.parse(TRUTH_SOCIAL_RSS)
        if not feed.entries:
            raise ValueError("empty feed")
        items = []
        cutoff = _cutoff()
        for entry in feed.entries:
            pub = entry.get("published_parsed")
            if pub:
                dt = datetime(*pub[:6], tzinfo=timezone.utc)
            else:
                dt = datetime.now(timezone.utc)
            if dt < cutoff:
                continue
            items.append(TrumpItem(
                source="truth_social",
                published_at=dt,
                title=_clean(entry.get("title", "")),
                content=_clean(entry.get("summary", "")),
                url=entry.get("link", ""),
            ))
        logger.info("Truth Social RSS: %d items", len(items))
        return items
    except Exception as e:
        logger.warning("Truth Social RSS failed: %s — trying CNN fallback", e)
        return _fetch_truth_social_cnn()


def _fetch_truth_social_cnn() -> list[TrumpItem]:
    try:
        resp = requests.get(CNN_TRUTH_ARCHIVE, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        posts = data if isinstance(data, list) else data.get("posts", [])
        cutoff = _cutoff()
        items = []
        for post in posts:
            ts = post.get("created_at") or post.get("timestamp", "")
            try:
                from dateutil import parser as dtparser
                dt = dtparser.parse(ts).replace(tzinfo=timezone.utc) if ts else datetime.now(timezone.utc)
            except Exception:
                dt = datetime.now(timezone.utc)
            if dt < cutoff:
                continue
            content = _clean(post.get("content") or post.get("text") or "")
            items.append(TrumpItem(
                source="truth_social",
                published_at=dt,
                title=content[:100],
                content=content,
                url=post.get("url", ""),
            ))
        logger.info("CNN Truth Social fallback: %d items", len(items))
        return items
    except Exception as e:
        logger.error("CNN Truth Social fallback also failed: %s", e)
        return []


def _fetch_news_feed(name: str, url: str) -> list[TrumpItem]:
    try:
        feed = feedparser.parse(url)
        cutoff = _cutoff()
        items = []
        for entry in feed.entries:
            pub = entry.get("published_parsed")
            if pub:
                dt = datetime(*pub[:6], tzinfo=timezone.utc)
            else:
                dt = datetime.now(timezone.utc)
            if dt < cutoff:
                continue
            item = TrumpItem(
                source=name,
                published_at=dt,
                title=_clean(entry.get("title", "")),
                content=_clean(entry.get("summary", "")),
                url=entry.get("link", ""),
            )
            if _is_trump_related(item):
                items.append(item)
        logger.info("Feed %s: %d relevant items", name, len(items))
        return items
    except Exception as e:
        logger.warning("Feed %s failed: %s", name, e)
        return []


def _fetch_whitehouse() -> list[TrumpItem]:
    try:
        resp = requests.get(WHITEHOUSE_URL, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        items = []
        cutoff = _cutoff(hours=24)
        for article in soup.select("article, .news-item, h2 a, h3 a")[:20]:
            link = article if article.name == "a" else article.find("a")
            if not link:
                continue
            href = link.get("href", "")
            if not href.startswith("http"):
                href = "https://www.whitehouse.gov" + href
            title = _clean(link.get_text())
            if not title:
                continue
            items.append(TrumpItem(
                source="whitehouse",
                published_at=datetime.now(timezone.utc),
                title=title,
                content="",
                url=href,
            ))
        logger.info("White House: %d items", len(items))
        return items[:10]
    except Exception as e:
        logger.warning("White House scrape failed: %s", e)
        return []


def _fetch_newsapi(api_key: str) -> list[TrumpItem]:
    try:
        resp = requests.get(
            NEWSAPI_URL,
            params={"q": "Trump", "sortBy": "publishedAt", "language": "en", "pageSize": 20},
            headers={"X-Api-Key": api_key},
            timeout=15,
        )
        resp.raise_for_status()
        articles = resp.json().get("articles", [])
        cutoff = _cutoff()
        items = []
        for a in articles:
            ts = a.get("publishedAt", "")
            try:
                from dateutil import parser as dtparser
                dt = dtparser.parse(ts).replace(tzinfo=timezone.utc)
            except Exception:
                dt = datetime.now(timezone.utc)
            if dt < cutoff:
                continue
            items.append(TrumpItem(
                source="newsapi",
                published_at=dt,
                title=_clean(a.get("title") or ""),
                content=_clean(a.get("description") or ""),
                url=a.get("url", ""),
            ))
        logger.info("NewsAPI: %d items", len(items))
        return items
    except Exception as e:
        logger.warning("NewsAPI failed: %s", e)
        return []


def fetch_all(newsapi_key: str = "") -> list[TrumpItem]:
    all_items: list[TrumpItem] = []

    truth_items = _fetch_truth_social_rss()
    all_items.extend(truth_items)

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(_fetch_news_feed, name, url): name for name, url in NEWS_FEEDS}
        futures[pool.submit(_fetch_whitehouse)] = "whitehouse"
        if newsapi_key:
            futures[pool.submit(_fetch_newsapi, newsapi_key)] = "newsapi"
        for future in as_completed(futures):
            try:
                all_items.extend(future.result())
            except Exception as e:
                logger.error("Fetch error: %s", e)

    all_items.sort(key=lambda x: x.published_at, reverse=True)
    all_items = _dedup(all_items)
    all_items = all_items[:30]

    logger.info("Total unique items after dedup: %d", len(all_items))
    return all_items
