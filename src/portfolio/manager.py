"""
Portfolio Management & Risk Engine
Tracks positions, enforces risk limits, manages 3% risk sizing
"""
import json
import logging
import os
from dataclasses import dataclass, asdict, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from threading import Lock

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

PORTFOLIO_FILE = DATA_DIR / "portfolio_state.json"
HISTORY_FILE = DATA_DIR / "trade_history.jsonl"
SIGNALS_FILE = DATA_DIR / "signals_log.jsonl"


@dataclass
class Position:
    ticker: str
    name: str
    entry_price: float
    entry_date: str
    quantity: int
    stop_loss: float
    target: float
    hold_days: int
    max_hold_days: int
    signal_id: str
    catalyst_type: str
    catalyst_expiry: str
    trailing_activated: bool = False
    highest_price: float = 0
    unrealized_pnl: float = 0
    unrealized_pnl_pct: float = 0

    def is_expired(self) -> bool:
        entry = datetime.fromisoformat(self.entry_date).date()
        return date.today() > entry + timedelta(days=self.max_hold_days)

    def days_held(self) -> int:
        entry = datetime.fromisoformat(self.entry_date).date()
        return (date.today() - entry).days

    def update_price(self, current_price: float):
        self.unrealized_pnl = (current_price - self.entry_price) * self.quantity
        self.unrealized_pnl_pct = (current_price - self.entry_price) / self.entry_price * 100
        if current_price > self.highest_price:
            self.highest_price = current_price


@dataclass
class TradeRecord:
    ticker: str
    name: str
    side: str  # BUY/SELL
    price: float
    quantity: int
    date: str
    signal_id: str
    exit_reason: str = ""
    pnl: float = 0
    pnl_pct: float = 0
    hold_days: int = 0


class PortfolioManager:
    """Manages positions, risk limits, and trade history"""

    def __init__(self, capital: float = 100000):
        self.capital = capital
        self.positions: Dict[str, Position] = {}
        self.history: List[TradeRecord] = []
        self.daily_pnl = 0.0
        self._lock = Lock()
        self._load()

    def _load(self):
        """Load portfolio state"""
        if PORTFOLIO_FILE.exists():
            try:
                with open(PORTFOLIO_FILE) as f:
                    data = json.load(f)
                self.capital = data.get("capital", self.capital)
                for p in data.get("positions", []):
                    self.positions[p["ticker"]] = Position(**p)
                logger.info(f"Loaded {len(self.positions)} positions")
            except Exception as e:
                logger.warning(f"Portfolio load failed: {e}")

        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE) as f:
                    for line in f:
                        self.history.append(TradeRecord(**json.loads(line)))
            except Exception as e:
                logger.warning(f"History load failed: {e}")

    def _save(self):
        """Save portfolio state"""
        with self._lock:
            data = {
                "capital": self.capital,
                "updated": datetime.now().isoformat(),
                "positions": [asdict(p) for p in self.positions.values()]
            }
            PORTFOLIO_FILE.write_text(json.dumps(data, indent=2))

    def _log_trade(self, record: TradeRecord):
        """Append to trade history"""
        with open(HISTORY_FILE, "a") as f:
            f.write(json.dumps(asdict(record)) + "\n")
        self.history.append(record)

    def _log_signal(self, signal: Dict):
        """Log signal for backtesting"""
        with open(SIGNALS_FILE, "a") as f:
            f.write(json.dumps(signal) + "\n")

    # ─────────────────────────────────────────────────────────────────────────
    # POSITION MANAGEMENT
    # ─────────────────────────────────────────────────────────────────────────

    def can_open_position(self, signal: Dict) -> tuple[bool, str]:
        """Check if new position can be opened"""
        trade = signal.get("trade", {})
        ticker = trade.get("ticker", "")

        # Already have position
        if ticker in self.positions:
            return False, f"Already holding {ticker}"

        # Max positions
        max_pos = int(os.getenv("MAX_POSITIONS", "5"))
        if len(self.positions) >= max_pos:
            return False, f"Max positions ({max_pos}) reached"

        # Sector limit
        sector_limit = int(os.getenv("MAX_PER_SECTOR", "2"))
        sector = self._get_sector(ticker)
        sector_count = sum(1 for p in self.positions.values() if self._get_sector(p.ticker) == sector)
        if sector_count >= sector_limit:
            return False, f"Sector limit ({sector_limit}) reached for {sector}"

        # Capital check
        required_margin = self._calculate_margin(trade)
        if required_margin > self.capital * 0.9:
            return False, "Insufficient capital"

        return True, "OK"

    def open_position(self, signal: Dict) -> Optional[Position]:
        """Open new position from signal"""
        can_open, reason = self.can_open_position(signal)
        if not can_open:
            logger.warning(f"Cannot open: {reason}")
            return None

        trade = signal["trade"]
        ticker = trade["ticker"]

        # Calculate position size (3% risk)
        risk_pct = float(os.getenv("RISK_PER_TRADE_PCT", "3"))
        risk_amount = self.capital * risk_pct / 100
        stop_loss_pct = trade["stop_loss_pct"]
        entry_price = self._parse_price_range(trade["entry_price_range"])
        stop_price = entry_price * (1 - stop_loss_pct / 100)
        qty = int(risk_amount / (entry_price - stop_price))

        if qty <= 0:
            return None

        # Round to lot size
        lot_size = self._get_lot_size(ticker)
        qty = (qty // lot_size) * lot_size
        if qty < lot_size:
            qty = lot_size

        position = Position(
            ticker=ticker,
            name=trade["name"],
            entry_price=entry_price,
            entry_date=date.today().isoformat(),
            quantity=qty,
            stop_loss=stop_price,
            target=entry_price * (1 + trade["target_pct"] / 100),
            hold_days=0,
            max_hold_days=trade.get("max_hold_days", 10),
            signal_id=signal["signal_id"],
            catalyst_type=signal["catalyst"]["type"],
            catalyst_expiry=trade.get("catalyst_expiry", ""),
            highest_price=entry_price
        )

        self.positions[ticker] = position
        self._save()

        # Log trade
        self._log_trade(TradeRecord(
            ticker=ticker,
            name=trade["name"],
            side="BUY",
            price=entry_price,
            quantity=qty,
            date=date.today().isoformat(),
            signal_id=signal["signal_id"]
        ))

        logger.info(f"Opened: {ticker} x{qty} @ {entry_price} (SL: {stop_price:.2f}, Target: {position.target:.2f})")
        return position

    def close_position(self, ticker: str, price: float, reason: str = "MANUAL") -> bool:
        """Close position"""
        if ticker not in self.positions:
            return False

        pos = self.positions[ticker]
        pnl = (price - pos.entry_price) * pos.quantity
        pnl_pct = (price - pos.entry_price) / pos.entry_price * 100
        hold_days = pos.days_held()

        # Log trade
        self._log_trade(TradeRecord(
            ticker=ticker,
            name=pos.name,
            side="SELL",
            price=price,
            quantity=pos.quantity,
            date=date.today().isoformat(),
            signal_id=pos.signal_id,
            exit_reason=reason,
            pnl=pnl,
            pnl_pct=pnl_pct,
            hold_days=hold_days
        ))

        self.daily_pnl += pnl
        del self.positions[ticker]
        self._save()

        logger.info(f"Closed: {ticker} @ {price} | PnL: {pnl:.0f} ({pnl_pct:.1f}%) | Reason: {reason}")
        return True

    def update_positions(self, prices: Dict[str, float]):
        """Update position prices and check exits"""
        to_close = []

        for ticker, pos in self.positions.items():
            price = prices.get(ticker)
            if not price:
                continue

            pos.update_price(price)

            # Check stop loss
            if price <= pos.stop_loss:
                to_close.append((ticker, price, "STOP_LOSS"))
                continue

            # Check target
            if price >= pos.target:
                to_close.append((ticker, price, "TARGET_HIT"))
                continue

            # Check max hold days
            if pos.is_expired():
                to_close.append((ticker, price, "MAX_HOLD_DAYS"))
                continue

            # Trailing stop
            if not pos.trailing_activated and pos.unrealized_pnl_pct >= 5:
                pos.trailing_activated = True
                pos.stop_loss = pos.highest_price * 0.98  # 2% trail
                logger.info(f"Trailing stop activated for {ticker}: {pos.stop_loss:.2f}")
            elif pos.trailing_activated and pos.highest_price * 0.98 > pos.stop_loss:
                pos.stop_loss = pos.highest_price * 0.98

        # Execute closes
        for ticker, price, reason in to_close:
            self.close_position(ticker, price, reason)

        self._save()

    def get_portfolio_summary(self) -> Dict:
        """Get portfolio summary for display"""
        total_invested = sum(p.entry_price * p.quantity for p in self.positions.values())
        total_current = 0
        total_pnl = 0

        positions = []
        for p in self.positions.values():
            positions.append({
                "ticker": p.ticker,
                "name": p.name,
                "entry": p.entry_price,
                "qty": p.quantity,
                "sl": p.stop_loss,
                "target": p.target,
                "days": p.days_held(),
                "max_days": p.max_hold_days,
                "unrealized_pnl": p.unrealized_pnl,
                "unrealized_pnl_pct": p.unrealized_pnl_pct,
                "catalyst": p.catalyst_type
            })

        return {
            "capital": self.capital,
            "invested": total_invested,
            "available": self.capital - total_invested,
            "positions": positions,
            "position_count": len(self.positions),
            "daily_pnl": self.daily_pnl,
            "total_pnl": sum(t.pnl for t in self.history if t.side == "SELL")
        }

    # ─────────────────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    def _calculate_margin(self, trade: Dict) -> float:
        entry = self._parse_price_range(trade.get("entry_price_range", "0"))
        qty = int(trade.get("position_size_pct", 3) / 100 * self.capital / entry)
        return entry * qty

    def _parse_price_range(self, price_range: str) -> float:
        """Parse '₹X - ₹Y' -> midpoint"""
        import re
        nums = re.findall(r'[\d,]+\.?\d*', price_range.replace(',', ''))
        if len(nums) >= 2:
            return (float(nums[0]) + float(nums[1])) / 2
        elif len(nums) == 1:
            return float(nums[0])
        return 0

    def _get_lot_size(self, ticker: str) -> int:
        """Get lot size for ticker (default 1 for equity)"""
        # F&O lot sizes would go here
        return 1

    def _get_sector(self, ticker: str) -> str:
        stock = self.mapper.universe.get(ticker)
        return stock.sector if stock else "UNKNOWN"


# Global instance
_portfolio: Optional[PortfolioManager] = None


def get_portfolio() -> PortfolioManager:
    global _portfolio
    if _portfolio is None:
        capital = float(os.getenv("TRADING_CAPITAL", "100000"))
        _portfolio = PortfolioManager(capital)
    return _portfolio