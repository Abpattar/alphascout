"""
AlphaScout Confidence Calibration
Remaps raw LLM confidence to calibrated confidence based on historical outcomes.

The LLM's "90% confidence" may not mean 90% actual win rate.
This module buckets signals by stated confidence, compares to actual outcomes,
and produces a calibration mapping. Signals below a minimum calibrated
confidence threshold are downgraded to WATCH/no-action.
"""
import json
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data"
CALIBRATION_FILE = DATA_DIR / "confidence_calibration.json"

# Minimum signals needed per bucket before calibration kicks in
# Problem 5: Require 30+ signals per bucket before trusting the AI's confidence
MIN_SIGNALS_PER_BUCKET = 30

# Minimum total signals before auto-execution is allowed at all
MIN_TOTAL_SIGNALS_FOR_AUTO = 50

# Default calibration (used when no data yet — identity mapping)
DEFAULT_CALIBRATION = {
    "60-69": {"raw_min": 60, "raw_max": 69, "calibrated": 55, "actual_wr": 0, "n": 0},
    "70-79": {"raw_min": 70, "raw_max": 79, "calibrated": 65, "actual_wr": 0, "n": 0},
    "80-89": {"raw_min": 80, "raw_max": 89, "calibrated": 75, "actual_wr": 0, "n": 0},
    "90-95": {"raw_min": 90, "raw_max": 95, "calibrated": 85, "actual_wr": 0, "n": 0},
    "96-100": {"raw_min": 96, "raw_max": 100, "calibrated": 90, "actual_wr": 0, "n": 0},
}


class ConfidenceCalibrator:
    """Maps raw LLM confidence to calibrated confidence using historical data."""

    def __init__(self):
        self.calibration: Dict[str, Dict] = {}
        self._load()

    def _load(self):
        if CALIBRATION_FILE.exists():
            try:
                with open(CALIBRATION_FILE) as f:
                    self.calibration = json.load(f)
                logger.info(f"Loaded calibration with {sum(b['n'] for b in self.calibration.values())} signals")
            except Exception:
                self.calibration = dict(DEFAULT_CALIBRATION)
        else:
            self.calibration = dict(DEFAULT_CALIBRATION)

    def _save(self):
        DATA_DIR.mkdir(exist_ok=True)
        with open(CALIBRATION_FILE, "w") as f:
            json.dump(self.calibration, f, indent=2)

    def calibrate_from_db(self) -> Dict:
        """Rebuild calibration mapping from all stored outcomes in the DB."""
        from src.storage.db import get_db
        db = get_db()
        data = db.get_outcomes_for_calibration()

        if not data:
            logger.info("No outcomes for calibration yet, using defaults")
            return self.calibration

        # Bucket by raw confidence
        buckets = defaultdict(lambda: {"total": 0, "wins": 0, "losses": 0, "pnl_sum": 0})

        for row in data:
            conf = row.get("confidence", 0)
            outcome = row.get("outcome", "OPEN")
            pnl = row.get("actual_pnl_pct", 0)

            bucket_key = self._bucket_key(conf)
            buckets[bucket_key]["total"] += 1
            if outcome == "WIN":
                buckets[bucket_key]["wins"] += 1
            elif outcome == "LOSS":
                buckets[bucket_key]["losses"] += 1
            buckets[bucket_key]["pnl_sum"] += pnl

        # Compute calibrated values
        for bucket_key, stats in buckets.items():
            total = stats["total"]
            wins = stats["wins"]
            actual_wr = wins / total * 100 if total else 0
            avg_pnl = stats["pnl_sum"] / total if total else 0

            # Calibrated confidence = actual win rate, clamped
            calibrated = max(30, min(95, int(actual_wr)))

            self.calibration[bucket_key] = {
                "raw_min": self._bucket_range(bucket_key)[0],
                "raw_max": self._bucket_range(bucket_key)[1],
                "calibrated": calibrated,
                "actual_wr": round(actual_wr, 1),
                "avg_pnl_pct": round(avg_pnl, 2),
                "n": total,
                "wins": wins,
                "losses": stats["losses"],
                "updated_at": datetime.now().isoformat(),
            }

        self._save()
        logger.info(f"Calibration updated from {len(data)} outcomes")
        return self.calibration

    def get_calibrated(self, raw_confidence: float) -> float:
        """Map raw LLM confidence to calibrated confidence."""
        bucket = self._bucket_key(raw_confidence)
        info = self.calibration.get(bucket, {})

        n = info.get("n", 0)
        if n >= MIN_SIGNALS_PER_BUCKET:
            return float(info.get("calibrated", raw_confidence))

        # Not enough data yet — use identity mapping with slight discount
        return max(raw_confidence - 5, 50)

    def should_auto_execute(self, raw_confidence: float, min_calibrated: float = 80) -> Tuple[bool, float, str]:
        """
        Check if a signal should auto-execute based on calibrated confidence.
        Problem 5: Requires large sample before trusting confidence for auto-execution.
        Returns (should_execute, calibrated_confidence, reason).
        """
        calibrated = self.get_calibrated(raw_confidence)
        bucket = self._bucket_key(raw_confidence)
        n = self.calibration.get(bucket, {}).get("n", 0)

        # Check minimum total signals across all buckets
        total_signals = sum(b.get("n", 0) for b in self.calibration.values())
        if total_signals < MIN_TOTAL_SIGNALS_FOR_AUTO:
            return False, calibrated, (
                f"Total signals too low ({total_signals}/{MIN_TOTAL_SIGNALS_FOR_AUTO}) — "
                f"need more data before auto-executing"
            )

        if n < MIN_SIGNALS_PER_BUCKET:
            return False, calibrated, f"Insufficient data ({n}/{MIN_SIGNALS_PER_BUCKET} signals in bucket)"

        if calibrated < min_calibrated:
            return False, calibrated, f"Calibrated {calibrated:.0f}% < min {min_calibrated}%"

        return True, calibrated, f"Calibrated {calibrated:.0f}% meets threshold (n={n})"

    def get_calibration_report(self) -> str:
        """Human-readable calibration report."""
        lines = ["CONFIDENCE CALIBRATION REPORT", "=" * 60]
        lines.append(f"{'Bucket':>12}  {'Signals':>7}  {'Win%':>6}  {'Calibrated':>10}  {'Avg PnL':>8}")
        lines.append("-" * 60)

        total_signals = 0
        total_wins = 0

        for bucket_key in sorted(self.calibration.keys()):
            b = self.calibration[bucket_key]
            n = b.get("n", 0)
            wr = b.get("actual_wr", 0)
            cal = b.get("calibrated", 0)
            avg_pnl = b.get("avg_pnl_pct", 0)
            total_signals += n
            total_wins += b.get("wins", 0)

            data_marker = "*" if n >= MIN_SIGNALS_PER_BUCKET else " "
            lines.append(
                f"{bucket_key:>12}  {n:>7}  {wr:>5.1f}%  {cal:>9}%{data_marker} {avg_pnl:>+7.2f}%"
            )

        lines.append("-" * 60)
        overall_wr = total_wins / total_signals * 100 if total_signals else 0
        lines.append(f"{'TOTAL':>12}  {total_signals:>7}  {overall_wr:>5.1f}%")
        lines.append("")
        lines.append("* = sufficient data (>=5 signals)")
        lines.append("Raw LLM '90% confidence' may actually be ~X% based on outcomes")

        return "\n".join(lines)

    @staticmethod
    def _bucket_key(confidence: float) -> str:
        c = int(confidence)
        if c < 70:
            return "60-69"
        elif c < 80:
            return "70-79"
        elif c < 90:
            return "80-89"
        elif c < 96:
            return "90-95"
        else:
            return "96-100"

    @staticmethod
    def _bucket_range(bucket_key: str) -> Tuple[int, int]:
        ranges = {
            "60-69": (60, 69),
            "70-79": (70, 79),
            "80-89": (80, 89),
            "90-95": (90, 95),
            "96-100": (96, 100),
        }
        return ranges.get(bucket_key, (60, 100))


# Singleton
_calibrator: Optional[ConfidenceCalibrator] = None


def get_calibrator() -> ConfidenceCalibrator:
    global _calibrator
    if _calibrator is None:
        _calibrator = ConfidenceCalibrator()
    return _calibrator
