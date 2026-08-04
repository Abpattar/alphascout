"""
AlphaScout Persistent Storage — SQLite
Stores articles, LLM outputs, signals, and outcomes.
Enables backtesting, calibration, and debugging.
"""
import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data"
DB_PATH = DATA_DIR / "alphascout.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_articles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url             TEXT UNIQUE NOT NULL,
    title           TEXT NOT NULL,
    source          TEXT NOT NULL,
    category        TEXT DEFAULT '',
    published_at    TEXT DEFAULT '',
    scraped_at      TEXT NOT NULL,
    content         TEXT DEFAULT '',
    summary         TEXT DEFAULT '',
    content_hash    TEXT DEFAULT '',
    extracted_tickers TEXT DEFAULT '[]',
    metadata        TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS llm_analysis (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id      INTEGER NOT NULL REFERENCES raw_articles(id),
    stage           TEXT NOT NULL,
    provider        TEXT NOT NULL,
    raw_output      TEXT NOT NULL,
    confidence_score REAL DEFAULT 0,
    signal_type     TEXT DEFAULT 'none',
    entry_price     REAL DEFAULT 0,
    target_price    REAL DEFAULT 0,
    stop_loss       REAL DEFAULT 0,
    risk_reward     REAL DEFAULT 0,
    created_at      TEXT NOT NULL,
    metadata        TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id       TEXT UNIQUE NOT NULL,
    article_id      INTEGER REFERENCES raw_articles(id),
    ticker          TEXT NOT NULL,
    name            TEXT DEFAULT '',
    direction       TEXT DEFAULT '',
    trade_type      TEXT DEFAULT '',
    confidence      REAL DEFAULT 0,
    calibrated_confidence REAL DEFAULT 0,
    entry_price     REAL DEFAULT 0,
    target_price    REAL DEFAULT 0,
    target_pct      REAL DEFAULT 0,
    stop_loss_price REAL DEFAULT 0,
    stop_loss_pct   REAL DEFAULT 0,
    risk_reward     REAL DEFAULT 0,
    hold_days       INTEGER DEFAULT 5,
    thesis          TEXT DEFAULT '',
    catalyst_type   TEXT DEFAULT '',
    catalyst_summary TEXT DEFAULT '',
    source_tier     INTEGER DEFAULT 3,
    ensemble_agreement INTEGER DEFAULT 0,
    executed        INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL,
    metadata        TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS outcomes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id       TEXT NOT NULL REFERENCES signals(signal_id),
    ticker          TEXT NOT NULL,
    entry_price     REAL NOT NULL,
    price_at_1d     REAL,
    price_at_3d     REAL,
    price_at_5d     REAL,
    price_at_7d     REAL,
    high_7d         REAL,
    low_7d          REAL,
    target_hit      INTEGER DEFAULT 0,
    stop_hit        INTEGER DEFAULT 0,
    actual_r_multiple REAL DEFAULT 0,
    actual_pnl_pct  REAL DEFAULT 0,
    outcome         TEXT DEFAULT 'OPEN',
    resolved_at     TEXT,
    metadata        TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_articles_url ON raw_articles(url);
CREATE INDEX IF NOT EXISTS idx_articles_source ON raw_articles(source);
CREATE INDEX IF NOT EXISTS idx_articles_scraped ON raw_articles(scraped_at);
CREATE INDEX IF NOT EXISTS idx_analysis_article ON llm_analysis(article_id);
CREATE INDEX IF NOT EXISTS idx_analysis_stage ON llm_analysis(stage);
CREATE INDEX IF NOT EXISTS idx_signals_ticker ON signals(ticker);
CREATE INDEX IF NOT EXISTS idx_signals_created ON signals(created_at);
CREATE INDEX IF NOT EXISTS idx_signals_executed ON signals(executed);
CREATE INDEX IF NOT EXISTS idx_outcomes_signal ON outcomes(signal_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_ticker ON outcomes(ticker);
CREATE INDEX IF NOT EXISTS idx_outcomes_outcome ON outcomes(outcome);
"""


class AlphaScoutDB:
    """Thread-safe SQLite storage for AlphaScout pipeline data."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(str(self.db_path), timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn

    @contextmanager
    def _cursor(self):
        conn = self._get_conn()
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    def _init_db(self):
        with self._cursor() as cur:
            cur.executescript(_SCHEMA)
        logger.info(f"Database initialized: {self.db_path}")

    def close(self):
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    # ─────────────────────────────────────────────────────────────────────
    # ARTICLES
    # ─────────────────────────────────────────────────────────────────────

    def store_article(self, article: Dict) -> Optional[int]:
        """Store a scraped article. Returns article id, or None if duplicate."""
        url = article.get("url", "")
        if not url:
            return None
        try:
            with self._cursor() as cur:
                cur.execute(
                    """INSERT OR IGNORE INTO raw_articles
                       (url, title, source, category, published_at, scraped_at,
                        content, summary, content_hash, extracted_tickers, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        url,
                        article.get("title", ""),
                        article.get("source", ""),
                        article.get("category", ""),
                        article.get("published", article.get("published_at", "")),
                        article.get("fetched_at", article.get("scraped_at", datetime.now().isoformat())),
                        article.get("content", ""),
                        article.get("summary", ""),
                        article.get("content_hash", ""),
                        json.dumps(article.get("extracted_tickers", [])),
                        json.dumps(article.get("metadata", {})),
                    ),
                )
                if cur.rowcount > 0:
                    return cur.lastrowid
                # Duplicate — fetch existing id
                cur.execute("SELECT id FROM raw_articles WHERE url = ?", (url,))
                row = cur.fetchone()
                return row["id"] if row else None
        except Exception as e:
            logger.warning(f"store_article failed: {e}")
            return None

    def store_articles_batch(self, articles: List[Dict]) -> int:
        """Store multiple articles. Returns count stored."""
        count = 0
        for a in articles:
            if self.store_article(a):
                count += 1
        logger.info(f"Stored {count}/{len(articles)} articles to DB")
        return count

    def get_article(self, article_id: int) -> Optional[Dict]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM raw_articles WHERE id = ?", (article_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_article_by_url(self, url: str) -> Optional[Dict]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM raw_articles WHERE url = ?", (url,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_recent_articles(self, hours: int = 48, limit: int = 200) -> List[Dict]:
        with self._cursor() as cur:
            cur.execute(
                """SELECT * FROM raw_articles
                   WHERE scraped_at > datetime('now', ? || ' hours')
                   ORDER BY scraped_at DESC LIMIT ?""",
                (f"-{hours}", limit),
            )
            return [dict(r) for r in cur.fetchall()]

    def count_articles(self) -> int:
        with self._cursor() as cur:
            cur.execute("SELECT COUNT(*) as cnt FROM raw_articles")
            return cur.fetchone()["cnt"]

    # ─────────────────────────────────────────────────────────────────────
    # LLM ANALYSIS
    # ─────────────────────────────────────────────────────────────────────

    def store_analysis(
        self,
        article_id: int,
        stage: str,
        provider: str,
        raw_output: Any,
        confidence_score: float = 0,
        signal_type: str = "none",
        entry_price: float = 0,
        target_price: float = 0,
        stop_loss: float = 0,
        risk_reward: float = 0,
        metadata: Optional[Dict] = None,
    ) -> Optional[int]:
        """Store an LLM analysis result."""
        try:
            output_str = json.dumps(raw_output) if not isinstance(raw_output, str) else raw_output
            with self._cursor() as cur:
                cur.execute(
                    """INSERT INTO llm_analysis
                       (article_id, stage, provider, raw_output, confidence_score,
                        signal_type, entry_price, target_price, stop_loss, risk_reward,
                        created_at, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        article_id, stage, provider, output_str,
                        confidence_score, signal_type,
                        entry_price, target_price, stop_loss, risk_reward,
                        datetime.now().isoformat(),
                        json.dumps(metadata or {}),
                    ),
                )
                return cur.lastrowid
        except Exception as e:
            logger.warning(f"store_analysis failed: {e}")
            return None

    def get_analyses_for_article(self, article_id: int) -> List[Dict]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM llm_analysis WHERE article_id = ? ORDER BY created_at",
                (article_id,),
            )
            return [dict(r) for r in cur.fetchall()]

    # ─────────────────────────────────────────────────────────────────────
    # SIGNALS
    # ─────────────────────────────────────────────────────────────────────

    def store_signal(self, signal: Dict, article_id: Optional[int] = None) -> Optional[int]:
        """Store a final trade signal."""
        trade = signal.get("trade", {})
        signal_id = signal.get("signal_id", "")
        if not signal_id:
            return None
        try:
            with self._cursor() as cur:
                cur.execute(
                    """INSERT OR IGNORE INTO signals
                       (signal_id, article_id, ticker, name, direction, trade_type,
                        confidence, calibrated_confidence, entry_price, target_price,
                        target_pct, stop_loss_price, stop_loss_pct, risk_reward,
                        hold_days, thesis, catalyst_type, catalyst_summary,
                        source_tier, ensemble_agreement, executed, created_at, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        signal_id,
                        article_id,
                        trade.get("ticker", ""),
                        trade.get("name", ""),
                        trade.get("direction", ""),
                        trade.get("trade_type", ""),
                        trade.get("confidence", 0),
                        trade.get("confidence", 0),  # starts equal to raw confidence
                        _parse_num(trade.get("entry_price_range", "0")),
                        _parse_num(trade.get("target_price", "0")),
                        trade.get("target_pct", 0),
                        _parse_num(trade.get("stop_loss_price", "0")),
                        trade.get("stop_loss_pct", 0),
                        trade.get("risk_reward_ratio", 0),
                        trade.get("hold_days", 5),
                        trade.get("thesis_one_line", ""),
                        signal.get("catalyst", {}).get("type", ""),
                        signal.get("article", {}).get("summary", signal.get("article", {}).get("title", "")),
                        3,  # default source tier
                        1 if signal.get("ensemble_agreement") else 0,
                        0,
                        signal.get("timestamp", datetime.now().isoformat()),
                        json.dumps(signal.get("metadata", {})),
                    ),
                )
                return cur.lastrowid if cur.rowcount > 0 else None
        except Exception as e:
            logger.warning(f"store_signal failed: {e}")
            return None

    def get_signal(self, signal_id: str) -> Optional[Dict]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM signals WHERE signal_id = ?", (signal_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_recent_signals(self, days: int = 30, limit: int = 100) -> List[Dict]:
        with self._cursor() as cur:
            cur.execute(
                """SELECT * FROM signals
                   WHERE created_at > datetime('now', ? || ' days')
                   ORDER BY created_at DESC LIMIT ?""",
                (f"-{days}", limit),
            )
            return [dict(r) for r in cur.fetchall()]

    def get_unresolved_signals(self, days: int = 14) -> List[Dict]:
        """Get signals that don't have outcomes yet."""
        with self._cursor() as cur:
            cur.execute(
                """SELECT s.* FROM signals s
                   LEFT JOIN outcomes o ON s.signal_id = o.signal_id
                   WHERE o.id IS NULL
                     AND s.created_at > datetime('now', ? || ' days')
                   ORDER BY s.created_at DESC""",
                (f"-{days}",),
            )
            return [dict(r) for r in cur.fetchall()]

    def mark_signal_executed(self, signal_id: str):
        with self._cursor() as cur:
            cur.execute(
                "UPDATE signals SET executed = 1 WHERE signal_id = ?", (signal_id,)
            )

    def update_signal_calibrated_confidence(self, signal_id: str, calibrated: float):
        with self._cursor() as cur:
            cur.execute(
                "UPDATE signals SET calibrated_confidence = ? WHERE signal_id = ?",
                (calibrated, signal_id),
            )

    def count_signals(self, days: int = 30) -> int:
        with self._cursor() as cur:
            cur.execute(
                """SELECT COUNT(*) as cnt FROM signals
                   WHERE created_at > datetime('now', ? || ' days')""",
                (f"-{days}",),
            )
            return cur.fetchone()["cnt"]

    # ─────────────────────────────────────────────────────────────────────
    # OUTCOMES
    # ─────────────────────────────────────────────────────────────────────

    def store_outcome(self, outcome: Dict) -> Optional[int]:
        """Store an outcome record for a signal."""
        try:
            with self._cursor() as cur:
                cur.execute(
                    """INSERT OR REPLACE INTO outcomes
                       (signal_id, ticker, entry_price, price_at_1d, price_at_3d,
                        price_at_5d, price_at_7d, high_7d, low_7d,
                        target_hit, stop_hit, actual_r_multiple, actual_pnl_pct,
                        outcome, resolved_at, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        outcome["signal_id"],
                        outcome["ticker"],
                        outcome["entry_price"],
                        outcome.get("price_at_1d"),
                        outcome.get("price_at_3d"),
                        outcome.get("price_at_5d"),
                        outcome.get("price_at_7d"),
                        outcome.get("high_7d"),
                        outcome.get("low_7d"),
                        outcome.get("target_hit", 0),
                        outcome.get("stop_hit", 0),
                        outcome.get("actual_r_multiple", 0),
                        outcome.get("actual_pnl_pct", 0),
                        outcome.get("outcome", "OPEN"),
                        outcome.get("resolved_at", datetime.now().isoformat()),
                        json.dumps(outcome.get("metadata", {})),
                    ),
                )
                return cur.lastrowid
        except Exception as e:
            logger.warning(f"store_outcome failed: {e}")
            return None

    def get_outcome(self, signal_id: str) -> Optional[Dict]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM outcomes WHERE signal_id = ?", (signal_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_all_outcomes(self, limit: int = 500, dedupe: bool = True) -> List[Dict]:
        """Get outcomes joined with signal info (confidence, created_at, name).

        dedupe=True collapses pre-cooldown duplicates: the same ticker signaled
        multiple times on the same day (e.g. 5× DEVIT from one run) is the same
        underlying trade with the same price path. Keep the highest-confidence
        signal per (ticker, day) so the sample isn't biased by duplicates.
        """
        with self._cursor() as cur:
            cur.execute(
                """SELECT o.*, s.confidence, s.created_at, s.name AS stock_name
                   FROM outcomes o
                   LEFT JOIN signals s ON s.signal_id = o.signal_id
                   ORDER BY o.resolved_at DESC LIMIT ?""",
                (limit,),
            )
            rows = [dict(r) for r in cur.fetchall()]
        return self._dedupe_by_ticker_day(rows) if dedupe else rows

    def get_outcomes_for_calibration(self) -> List[Dict]:
        """Get signals joined with outcomes for calibration analysis,
        deduplicated to one representative signal per (ticker, day)."""
        with self._cursor() as cur:
            cur.execute(
                """SELECT s.signal_id, s.ticker, s.confidence, s.calibrated_confidence,
                          s.risk_reward, s.target_pct, s.stop_loss_pct, s.created_at,
                          o.outcome, o.actual_r_multiple, o.actual_pnl_pct,
                          o.target_hit, o.stop_hit, o.high_7d, o.low_7d
                   FROM signals s
                   JOIN outcomes o ON s.signal_id = o.signal_id
                   WHERE o.outcome != 'OPEN'
                   ORDER BY s.created_at"""
            )
            rows = [dict(r) for r in cur.fetchall()]
        return self._dedupe_by_ticker_day(rows)

    @staticmethod
    def _dedupe_by_ticker_day(rows: List[Dict]) -> List[Dict]:
        """Collapse same-ticker/same-day signals to one representative: highest
        confidence, tie-broken by earliest signal_id (creation order)."""
        best: Dict[tuple, Dict] = {}
        for r in rows:
            day = (r.get("created_at") or r.get("resolved_at") or "")[:10]
            key = (r.get("ticker"), day)
            cur = best.get(key)
            if cur is None:
                best[key] = r
                continue
            cur_conf = cur.get("confidence") or 0
            new_conf = r.get("confidence") or 0
            if new_conf > cur_conf or (
                new_conf == cur_conf
                and (r.get("signal_id") or "") < (cur.get("signal_id") or "")
            ):
                best[key] = r
        return [best[k] for k in sorted(best, key=lambda k: best[k].get("created_at") or "")]

    # ─────────────────────────────────────────────────────────────────────
    # STATS
    # ─────────────────────────────────────────────────────────────────────

    def get_stats(self) -> Dict:
        """Get overall database statistics."""
        stats = {}
        with self._cursor() as cur:
            cur.execute("SELECT COUNT(*) as cnt FROM raw_articles")
            stats["articles"] = cur.fetchone()["cnt"]

            cur.execute("SELECT COUNT(*) as cnt FROM llm_analysis")
            stats["llm_analyses"] = cur.fetchone()["cnt"]

            cur.execute("SELECT COUNT(*) as cnt FROM signals")
            stats["signals"] = cur.fetchone()["cnt"]

            cur.execute("SELECT COUNT(*) as cnt FROM outcomes")
            stats["outcomes"] = cur.fetchone()["cnt"]

            cur.execute("SELECT COUNT(*) as cnt FROM outcomes WHERE outcome = 'WIN'")
            stats["wins"] = cur.fetchone()["cnt"]

            cur.execute("SELECT COUNT(*) as cnt FROM outcomes WHERE outcome = 'LOSS'")
            stats["losses"] = cur.fetchone()["cnt"]

            if stats["wins"] + stats["losses"] > 0:
                stats["win_rate"] = round(
                    stats["wins"] / (stats["wins"] + stats["losses"]) * 100, 1
                )
            else:
                stats["win_rate"] = 0

        return stats


# ─────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────

def _parse_num(val) -> float:
    """Extract first number from a string like '₹125 - ₹130' or return float."""
    if isinstance(val, (int, float)):
        return float(val)
    if not val:
        return 0
    import re
    nums = re.findall(r'[\d,]+\.?\d*', str(val).replace(',', ''))
    if nums:
        return float(nums[0])
    return 0


# ─────────────────────────────────────────────────────────────────────────
# SINGLETON
# ─────────────────────────────────────────────────────────────────────────

_db: Optional[AlphaScoutDB] = None


def get_db() -> AlphaScoutDB:
    global _db
    if _db is None:
        _db = AlphaScoutDB()
    return _db
