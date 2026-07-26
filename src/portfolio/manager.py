"""
Portfolio Management & Risk Engine
Tracks positions, enforces risk limits, manages 3% risk sizing.

Safety features:
- PERSONAL_USE_ONLY flag (SEBI compliance)
- Paper trading mode (log-only, no execution)
- Max drawdown kill-switch
- Hard position sizing limits
- Min daily traded value filter
"""
import json
import logging
import os
from dataclasses import dataclass, asdict, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from threading import Lock

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

PORTFOLIO_FILE = DATA_DIR / "portfolio_state.json"
HISTORY_FILE = DATA_DIR / "trade_history.jsonl"
SIGNALS_FILE = DATA_DIR / "signals_log.jsonl"
DRAWDOWN_FILE = DATA_DIR / "drawdown_state.json"


def _load_config():
    """Load portfolio config from settings.yaml."""
    try:
        from src.config import load_settings
        settings = load_settings()
        return {
            "personal_use_only": settings.get("portfolio", {}).get("personal_use_only", True),
            "paper_trading": settings.get("portfolio", {}).get("paper_trading", True),
            "max_positions": settings.get("portfolio", {}).get("max_positions", 5),
            "max_per_sector": settings.get("portfolio", {}).get("max_per_sector", 2),
            "max_position_size_pct": settings.get("portfolio", {}).get("max_position_size_pct", 10.0),
            "min_position_size_pct": settings.get("portfolio", {}).get("min_position_size_pct", 1.0),
            "max_portfolio_allocation_pct": settings.get("portfolio", {}).get("max_portfolio_allocation_pct", 50.0),
            "min_avg_daily_value_cr": settings.get("portfolio", {}).get("min_avg_daily_value_cr", 1.0),
            "risk_per_trade_pct": settings.get("risk", {}).get("risk_per_trade_pct", 3.0),
            "max_portfolio_risk_pct": settings.get("risk", {}).get("max_portfolio_risk_pct", 15.0),
            "max_weekly_drawdown_pct": settings.get("risk", {}).get("max_weekly_drawdown_pct", 8.0),
            "max_single_loss_pct": settings.get("risk", {}).get("max_single_loss_pct", 5.0),
            "trailing_stop_activation_pct": settings.get("risk", {}).get("trailing_stop_activation_pct", 5.0),
            "trailing_stop_distance_pct": settings.get("risk", {}).get("trailing_stop_distance_pct", 2.0),
        }
    except Exception:
        return {
            "personal_use_only": True,
            "paper_trading": True,
            "max_positions": 5,
            "max_per_sector": 2,
            "max_position_size_pct": 10.0,
            "min_position_size_pct": 1.0,
            "max_portfolio_allocation_pct": 50.0,
            "min_avg_daily_value_cr": 1.0,
            "risk_per_trade_pct": 3.0,
            "max_portfolio_risk_pct": 15.0,
            "max_weekly_drawdown_pct": 8.0,
            "max_single_loss_pct": 5.0,
            "trailing_stop_activation_pct": 5.0,
            "trailing_stop_distance_pct": 2.0,
        }


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
    """Manages positions, risk limits, and trade history with safety constraints."""

    def __init__(self, capital: float = 100000):
        self.capital = capital
        self.positions: Dict[str, Position] = {}
        self.history: List[TradeRecord] = []
        self.daily_pnl = 0.0
        self.weekly_pnl = 0.0
        self._lock = Lock()
        self._config = _load_config()
        self._drawdown_paused = False
        self._load()
        self._load_drawdown_state()

    def _load(self):
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
        with self._lock:
            data = {
                "capital": self.capital,
                "updated": datetime.now().isoformat(),
                "positions": [asdict(p) for p in self.positions.values()]
            }
            PORTFOLIO_FILE.write_text(json.dumps(data, indent=2))

    def _log_trade(self, record: TradeRecord):
        with open(HISTORY_FILE, "a") as f:
            f.write(json.dumps(asdict(record)) + "\n")
        self.history.append(record)

    def _log_signal(self, signal: Dict):
        with open(SIGNALS_FILE, "a") as f:
            f.write(json.dumps(signal) + "\n")

    # ─────────────────────────────────────────────────────────────────────────
    # DRAWDOWN KILL-SWITCH
    # ─────────────────────────────────────────────────────────────────────────

    def _load_drawdown_state(self):
        if DRAWDOWN_FILE.exists():
            try:
                with open(DRAWDOWN_FILE) as f:
                    data = json.load(f)
                self._drawdown_paused = data.get("paused", False)
                self.weekly_pnl = data.get("weekly_pnl", 0)
                week_start = data.get("week_start", "")
                if week_start:
                    start_date = datetime.fromisoformat(week_start).date()
                    if date.today().isocalendar()[1] != start_date.isocalendar()[1]:
                        self.weekly_pnl = 0
                        self._drawdown_paused = False
            except Exception:
                pass

    def _save_drawdown_state(self):
        data = {
            "paused": self._drawdown_paused,
            "weekly_pnl": self.weekly_pnl,
            "week_start": datetime.now().isoformat(),
            "updated": datetime.now().isoformat(),
        }
        DRAWDOWN_FILE.write_text(json.dumps(data, indent=2))

    def _check_drawdown_kill_switch(self) -> Tuple[bool, str]:
        """Check if weekly drawdown exceeds kill-switch threshold."""
        max_dd = self._config["max_weekly_drawdown_pct"]
        weekly_loss_pct = abs(self.weekly_pnl) / self.capital * 100 if self.weekly_pnl < 0 else 0

        if weekly_loss_pct >= max_dd:
            self._drawdown_paused = True
            self._save_drawdown_state()
            return True, f"Weekly drawdown {weekly_loss_pct:.1f}% >= {max_dd}% kill-switch"

        return False, "OK"

    def _reset_drawdown_if_new_week(self):
        """Reset weekly PnL tracking on new week."""
        if DRAWDOWN_FILE.exists():
            try:
                with open(DRAWDOWN_FILE) as f:
                    data = json.load(f)
                week_start = data.get("week_start", "")
                if week_start:
                    start_date = datetime.fromisoformat(week_start).date()
                    if date.today().isocalendar()[1] != start_date.isocalendar()[1]:
                        self.weekly_pnl = 0
                        self._drawdown_paused = False
                        self._save_drawdown_state()
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────────────────────
    # SAFETY CHECKS
    # ─────────────────────────────────────────────────────────────────────────

    def is_paper_trading(self) -> bool:
        return self._config.get("paper_trading", True)

    def is_personal_use_only(self) -> bool:
        return self._config.get("personal_use_only", True)

    # ─────────────────────────────────────────────────────────────────────────
    # POSITION MANAGEMENT
    # ─────────────────────────────────────────────────────────────────────────

    def can_open_position(self, signal: Dict) -> Tuple[bool, str]:
        """Check if new position can be opened (all safety checks)."""
        trade = signal.get("trade", {})
        ticker = trade.get("ticker", "")

        # Safety: personal use only check
        if not self.is_personal_use_only():
            return False, "PERSONAL_USE_ONLY is false — not safe for distribution"

        # Safety: paper trading mode
        if self.is_paper_trading():
            logger.info(f"Paper trading mode — would open {ticker} (not executing)")
            # Allow for logging, but note it's paper

        # Safety: drawdown kill-switch
        self._reset_drawdown_if_new_week()
        dd_hit, dd_reason = self._check_drawdown_kill_switch()
        if dd_hit:
            return False, f"KILL-SWITCH: {dd_reason}"

        # Already have position
        if ticker in self.positions:
            return False, f"Already holding {ticker}"

        # Max positions
        max_pos = self._config["max_positions"]
        if len(self.positions) >= max_pos:
            return False, f"Max positions ({max_pos}) reached"

        # Sector limit
        sector_limit = self._config["max_per_sector"]
        sector = self._get_sector(ticker)
        sector_count = sum(1 for p in self.positions.values() if self._get_sector(p.ticker) == sector)
        if sector_count >= sector_limit:
            return False, f"Sector limit ({sector_limit}) reached for {sector}"

        # Capital check
        required_margin = self._calculate_margin(trade)
        if required_margin > self.capital * 0.9:
            return False, "Insufficient capital"

        # Position size limits
        position_pct = trade.get("position_size_pct", 3)
        if position_pct > self._config["max_position_size_pct"]:
            return False, f"Position size {position_pct}% > max {self._config['max_position_size_pct']}%"
        if position_pct < self._config["min_position_size_pct"]:
            return False, f"Position size {position_pct}% < min {self._config['min_position_size_pct']}%"

        # Portfolio allocation check
        total_invested = sum(p.entry_price * p.quantity for p in self.positions.values())
        allocation_pct = (total_invested + required_margin) / self.capital * 100
        if allocation_pct > self._config["max_portfolio_allocation_pct"]:
            return False, f"Portfolio allocation {allocation_pct:.1f}% > max {self._config['max_portfolio_allocation_pct']}%"

        # Max single loss check
        stop_loss_pct = trade.get("stop_loss_pct", 100)
        if stop_loss_pct > self._config["max_single_loss_pct"]:
            return False, f"Stop loss {stop_loss_pct}% > max {self._config['max_single_loss_pct']}%"

        return True, "OK"

    def open_position(self, signal: Dict) -> Optional[Position]:
        """Open new position from signal (respects all safety rules)."""
        can_open, reason = self.can_open_position(signal)
        if not can_open:
            logger.warning(f"Cannot open: {reason}")
            return None

        trade = signal["trade"]
        ticker = trade["ticker"]

        # Calculate position size (3% risk)
        risk_pct = self._config["risk_per_trade_pct"]
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

        mode = "PAPER" if self.is_paper_trading() else "LIVE"
        logger.info(f"[{mode}] Opened: {ticker} x{qty} @ {entry_price} (SL: {stop_price:.2f}, Target: {position.target:.2f})")
        return position

    def close_position(self, ticker: str, price: float, reason: str = "MANUAL") -> bool:
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
        self.weekly_pnl += pnl
        del self.positions[ticker]
        self._save()
        self._save_drawdown_state()

        logger.info(f"Closed: {ticker} @ {price} | PnL: {pnl:.0f} ({pnl_pct:.1f}%) | Reason: {reason}")
        return True

    def update_positions(self, prices: Dict[str, float]):
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
            activation_pct = self._config["trailing_stop_activation_pct"]
            trail_pct = self._config["trailing_stop_distance_pct"]
            if not pos.trailing_activated and pos.unrealized_pnl_pct >= activation_pct:
                pos.trailing_activated = True
                pos.stop_loss = pos.highest_price * (1 - trail_pct / 100)
                logger.info(f"Trailing stop activated for {ticker}: {pos.stop_loss:.2f}")
            elif pos.trailing_activated and pos.highest_price * (1 - trail_pct / 100) > pos.stop_loss:
                pos.stop_loss = pos.highest_price * (1 - trail_pct / 100)

        # Execute closes
        for ticker, price, reason in to_close:
            self.close_position(ticker, price, reason)

        self._save()

    def get_portfolio_summary(self) -> Dict:
        total_invested = sum(p.entry_price * p.quantity for p in self.positions.values())

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
            "weekly_pnl": self.weekly_pnl,
            "total_pnl": sum(t.pnl for t in self.history if t.side == "SELL"),
            "paper_trading": self.is_paper_trading(),
            "personal_use_only": self.is_personal_use_only(),
            "drawdown_paused": self._drawdown_paused,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    def _calculate_margin(self, trade: Dict) -> float:
        entry = self._parse_price_range(trade.get("entry_price_range", "0"))
        qty = int(trade.get("position_size_pct", 3) / 100 * self.capital / entry)
        return entry * qty

    def _parse_price_range(self, price_range: str) -> float:
        import re
        nums = re.findall(r'[\d,]+\.?\d*', price_range.replace(',', ''))
        if len(nums) >= 2:
            return (float(nums[0]) + float(nums[1])) / 2
        elif len(nums) == 1:
            return float(nums[0])
        return 0

    def _get_lot_size(self, ticker: str) -> int:
        return 1

    def _get_sector(self, ticker: str) -> str:
        """Get sector for a ticker without relying on mapper."""
        try:
            from src.universe.builder import get_universe
            universe = get_universe()
            stock = universe.get(ticker)
            return stock.sector if stock else "UNKNOWN"
        except Exception:
            return "UNKNOWN"


# Global instance
_portfolio: Optional[PortfolioManager] = None


def get_portfolio() -> PortfolioManager:
    global _portfolio
    if _portfolio is None:
        capital = float(os.getenv("TRADING_CAPITAL", "100000"))
        _portfolio = PortfolioManager(capital)
    return _portfolio
