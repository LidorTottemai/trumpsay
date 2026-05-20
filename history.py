import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

SEED_EVENTS = [
    ("2025-04-02", "Liberation Day — sweeping tariffs on 180+ countries announced",
     "tariff,global,trade,liberation", "news", -4.84, "DOWN",
     "Largest tariff action in modern history; markets crashed on uncertainty"),
    ("2025-04-09", "Trump announces 90-day tariff pause for most countries",
     "tariff,pause,trade,relief", "news", 9.52, "UP",
     "Largest single-day S&P gain in years; relief rally on pause announcement"),
    ("2025-05-12", "US-China trade truce reached in Geneva; tariffs cut to 30%",
     "china,trade,deal,tariff,truce,geneva", "news", 3.26, "UP",
     "90-day truce, US tariffs on China cut from 145% to 30%"),
    ("2025-01-20", "Trump inauguration day; executive orders on energy and borders",
     "inauguration,executive order,energy,border", "news", 1.21, "UP",
     "Markets welcomed deregulation signals and business-friendly rhetoric"),
    ("2025-02-10", "Trump threatens 25% tariff on steel and aluminum imports",
     "tariff,steel,aluminum,metals", "news", -0.53, "DOWN",
     "Manufacturing stocks fell; retaliatory concerns weighed on market"),
    ("2025-03-04", "25% tariffs on Canada and Mexico take effect",
     "tariff,canada,mexico,trade", "news", -1.78, "DOWN",
     "Supply chain concerns; auto sector led decline"),
    ("2025-04-22", "Trump attacks Fed Chair Powell, demands rate cuts",
     "federal reserve,powell,rate,fed", "news", -2.24, "DOWN",
     "Dollar weakened; investors worried about Fed independence"),
    ("2025-05-08", "US-UK trade framework agreement announced",
     "uk,trade,deal,agreement", "news", 0.58, "UP",
     "Limited but positive signal; boosted sentiment for further deals"),
    ("2025-01-23", "Trump signs executive order on AI and crypto deregulation",
     "crypto,ai,deregulation,executive order,technology", "news", 1.74, "UP",
     "Tech and crypto sectors surged; deregulation seen as growth catalyst"),
    ("2025-02-03", "Emergency tariffs on Canada, Mexico, China announced",
     "tariff,china,canada,mexico,trade war", "news", -1.92, "DOWN",
     "Broad market decline; trade war fears escalated"),
    ("2025-03-26", "25% tariff on imported autos announced",
     "tariff,auto,cars,automobile", "news", -1.12, "DOWN",
     "Auto stocks fell sharply; Ford, GM, Stellantis hit hard"),
    ("2025-04-11", "Trump exempts smartphones and laptops from China tariffs",
     "tariff,china,tech,smartphones,laptops,exemption", "news", 2.14, "UP",
     "Apple and tech hardware companies surged on tariff carve-out"),
    ("2025-05-15", "Trump threatens 50% tariffs on EU goods",
     "tariff,eu,europe,trade", "news", -0.67, "DOWN",
     "European stocks fell more than US; dollar strengthened"),
    ("2025-05-19", "Trump-Saudi Arabia mega investment deal signed",
     "saudi,investment,deal,energy", "news", 0.44, "UP",
     "Defense and energy stocks gained; $600B investment commitment"),
    ("2025-01-30", "Trump threatens to take over Greenland and Panama Canal",
     "greenland,panama,geopolitical,territory", "news", -0.41, "DOWN",
     "Geopolitical uncertainty; minimal direct market impact"),
    ("2025-03-13", "Trump threatens 200% tariff on EU wine and spirits",
     "tariff,eu,wine,spirits,retaliation", "news", -0.89, "DOWN",
     "Consumer staples and luxury goods stocks affected"),
    ("2025-04-29", "Trump signs executive order easing auto emission rules",
     "auto,deregulation,executive order,energy", "news", 0.91, "UP",
     "US automakers rallied; energy sector also gained"),
    ("2025-02-18", "DOGE announces federal workforce cuts; 75,000 jobs eliminated",
     "doge,elon,government,spending,budget", "news", 0.23, "NEUTRAL",
     "Mixed reaction; fiscal hawks positive, government contractors sold off"),
    ("2025-03-20", "Trump calls for zero interest rates, blames Powell",
     "federal reserve,powell,rate,interest,fed", "news", -1.05, "DOWN",
     "Rate-sensitive stocks fell; uncertainty about Fed independence grew"),
    ("2025-04-14", "Trump proposes 25% tariff on foreign-made semiconductors",
     "tariff,semiconductor,chip,technology", "news", -1.43, "DOWN",
     "Semiconductor ETF dropped 3%; supply chain concerns"),
    ("2025-05-06", "Trump threatens sanctions on Russia if no Ukraine ceasefire",
     "russia,ukraine,sanctions,geopolitical,war", "news", 0.18, "NEUTRAL",
     "Defense stocks up slightly; energy prices volatile"),
    ("2025-04-04", "China retaliates with 34% tariffs on US goods",
     "china,retaliation,tariff,trade war", "news", -5.97, "DOWN",
     "Second consecutive massive sell-off; S&P entered correction territory"),
    ("2025-04-07", "Trump doubles down on tariffs, says markets will 'do great'",
     "tariff,trade war,confidence,market", "news", -0.23, "DOWN",
     "Brief intraday recovery but closed lower; credibility concerns"),
    ("2025-05-02", "Trump signs executive order cutting corporate tax to 15%",
     "tax,corporate,deregulation,executive order,fiscal", "news", 2.56, "UP",
     "Broad market rally; financial sector led gains"),
    ("2025-01-26", "Trump threatens Colombia with tariffs over deportation flights",
     "tariff,colombia,immigration,threat", "news", -0.12, "NEUTRAL",
     "Short-lived threat; Colombia quickly reversed course"),
    ("2025-03-04", "Trump freezes foreign aid; major budget cuts announced",
     "foreign aid,budget,spending,government", "news", 0.05, "NEUTRAL",
     "Limited direct market impact; defense contractors slightly negative"),
    ("2025-04-17", "Trump exempts pharma from new tariffs, signals future action",
     "tariff,pharma,pharmaceutical,healthcare,exemption", "news", 1.31, "UP",
     "Healthcare sector rallied on exemption; temporary relief"),
    ("2025-05-09", "Trump and Xi speak by phone; trade talks to resume",
     "china,xi,trade,talks,diplomacy", "news", 1.62, "UP",
     "Optimism on de-escalation; risk assets gained"),
    ("2025-01-21", "Trump pardons January 6 defendants",
     "pardon,january 6,politics", "news", 0.34, "NEUTRAL",
     "Limited market reaction; political rather than economic event"),
    ("2025-04-23", "Treasury Secretary Bessent signals tariff negotiations ongoing",
     "tariff,treasury,negotiation,trade,bessent", "news", 2.03, "UP",
     "Reassurance that tariffs are negotiating tools, not permanent policy"),
]


CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL,
    summary     TEXT NOT NULL,
    keywords    TEXT NOT NULL,
    source      TEXT NOT NULL,
    sp500_pct   REAL,
    direction   TEXT,
    notes       TEXT
);
"""


class HistoryStore:
    def __init__(self, db_path: str = "data/history.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(CREATE_TABLE)
            count = conn.execute("SELECT COUNT(*) FROM events WHERE sp500_pct IS NOT NULL").fetchone()[0]
            if count == 0:
                self._seed(conn)
                logger.info("Seeded historical database with %d events", len(SEED_EVENTS))

    def _seed(self, conn: sqlite3.Connection) -> None:
        conn.executemany(
            "INSERT INTO events (date, summary, keywords, source, sp500_pct, direction, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            SEED_EVENTS,
        )

    def find_similar(self, keywords: list[str], limit: int = 5) -> list[dict]:
        if not keywords:
            return []
        normalized = [kw.lower().strip() for kw in keywords]
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE sp500_pct IS NOT NULL ORDER BY date DESC"
            ).fetchall()
        scored = []
        for row in rows:
            row_keywords = set(k.strip() for k in row["keywords"].split(","))
            overlap = sum(1 for kw in normalized if any(kw in rk or rk in kw for rk in row_keywords))
            if overlap > 0:
                scored.append((overlap, dict(row)))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:limit]]

    def record_prediction(self, date: str, summary: str, keywords: list[str]) -> int:
        kw_str = ",".join(keywords)
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO events (date, summary, keywords, source) VALUES (?, ?, ?, 'prediction')",
                (date, summary, kw_str),
            )
            return cursor.lastrowid

    def record_outcome(self, event_id: int, sp500_pct: float) -> None:
        direction = "UP" if sp500_pct > 0.3 else ("DOWN" if sp500_pct < -0.3 else "NEUTRAL")
        with self._connect() as conn:
            conn.execute(
                "UPDATE events SET sp500_pct = ?, direction = ? WHERE id = ?",
                (sp500_pct, direction, event_id),
            )
        logger.info("Recorded outcome for event %d: %.2f%% (%s)", event_id, sp500_pct, direction)

    def extract_keywords(self, items) -> list[str]:
        TOPIC_KEYWORDS = {
            "tariff", "tariffs", "trade", "china", "eu", "europe", "mexico", "canada",
            "uk", "russia", "ukraine", "sanctions", "federal reserve", "powell", "rate",
            "interest rate", "executive order", "deregulation", "tax", "crypto", "bitcoin",
            "tech", "technology", "semiconductor", "auto", "automobile", "energy", "oil",
            "defense", "military", "nato", "deal", "agreement", "negotiation", "pause",
            "exemption", "retaliation", "inflation", "recession", "gdp", "jobs", "doge",
            "elon", "spending", "budget", "debt", "pharma", "healthcare",
        }
        found = set()
        for item in items:
            text = (item.title + " " + item.content).lower()
            for kw in TOPIC_KEYWORDS:
                if kw in text:
                    found.add(kw)
        return list(found)
