"""Offline tests for circuit-history classification (Problem 8).

Only LOWER-circuit days should count against exit liquidity; upper circuits
must be ignored. yfinance is mocked — no network access.
"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

import src.universe.builder as builder


def _hist(closes):
    idx = pd.date_range("2026-07-01", periods=len(closes), freq="D")
    return pd.DataFrame({"Close": closes}, index=idx)


def _patch_yf(closes):
    mock_ticker = MagicMock()
    # _yf_call_with_timeout calls t.history via a wrapper; patch the ticker's history
    mock_ticker.history.return_value = _hist(closes)
    return patch.object(builder.yf, "Ticker", return_value=mock_ticker)


class TestCircuitHistory:
    def test_lower_circuit_5pct_counted(self):
        with _patch_yf([100, 95]):  # -5% day
            info = builder.check_circuit_history("X.NS", days=30)
        assert info["has_circuit_hits"] is True
        assert info["circuit_days"] == 1
        assert info["max_lower_circuit_pct"] >= 4.8

    def test_lower_circuit_10pct_counted(self):
        with _patch_yf([100, 90]):  # -10% day
            info = builder.check_circuit_history("X.NS", days=30)
        assert info["circuit_days"] == 1

    def test_upper_circuit_NOT_counted(self):
        with _patch_yf([100, 105]):  # +5% day (upper circuit)
            info = builder.check_circuit_history("X.NS", days=30)
        assert info["has_circuit_hits"] is False
        assert info["circuit_days"] == 0

    def test_mixed_up_and_down_only_down_counts(self):
        closes = [100, 105, 110.25, 104.74]  # up, up, then ~-5%
        with _patch_yf(closes):
            info = builder.check_circuit_history("X.NS", days=30)
        assert info["circuit_days"] == 1

    def test_normal_moves_not_counted(self):
        with _patch_yf([100, 102, 101, 103]):
            info = builder.check_circuit_history("X.NS", days=30)
        assert info["has_circuit_hits"] is False

    def test_empty_history(self):
        with _patch_yf([]):
            info = builder.check_circuit_history("X.NS", days=30)
        assert info == {"has_circuit_hits": False, "circuit_days": 0,
                        "max_lower_circuit_pct": 0}
