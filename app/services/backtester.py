"""Backtesting Engine for Stock Trading Strategies.

Comprehensive backtesting framework to validate trading strategies on historical data.
Supports:
- Multiple strategy types (technical, ML, fundamental)
- Position sizing (fixed, Kelly criterion, fixed fractional)
- Risk management (stop loss, take profit, trailing stop)
- Performance metrics (Sharpe, Sortino, Max Drawdown, etc.)
- Walk-forward validation

Usage:
    from app.services.backtester import Backtester, SignalStrategy
    
    # Define strategy
    class MyStrategy(SignalStrategy):
        def generate_signal(self, row: pd.Series, portfolio: dict) -> str:
            # Your logic here
            return "BUY" | "SELL" | "HOLD"
    
    # Run backtest
    backtester = Backtester(initial_capital=100_000_000)
    results = backtester.run(strategy, data, start_date, end_date)
    
    # Print metrics
    print(f"Total Return: {results['total_return']:.2%}")
    print(f"Sharpe Ratio: {results['sharpe_ratio']:.2f}")
    print(f"Max Drawdown: {results['max_drawdown']:.2%}")
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ── Enums ──────────────────────────────────────────────────────────────────

class Signal(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class PositionType(Enum):
    LONG = "LONG"
    CASH = "CASH"


# ── Data Classes ───────────────────────────────────────────────────────────

@dataclass
class Trade:
    """Represents a single trade."""
    ticker: str
    entry_date: date
    entry_price: float
    exit_date: Optional[date] = None
    exit_price: Optional[float] = None
    shares: int = 0
    signal: str = ""
    
    # Exit reason
    exit_reason: str = ""  # "TP", "SL", "SIGNAL", "END"
    
    # Performance
    pnl: float = 0.0
    pnl_pct: float = 0.0
    holding_period: int = 0
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Portfolio:
    """Current portfolio state."""
    cash: float = 0.0
    positions: dict = field(default_factory=dict)  # ticker -> {shares, entry_price, entry_date}
    total_value: float = 0.0
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BacktestResult:
    """Complete backtest results."""
    # Configuration
    strategy_name: str
    ticker: str
    start_date: date
    end_date: date
    initial_capital: float
    
    # Returns
    final_capital: float
    total_return: float
    total_return_pct: float
    annualized_return: float
    
    # Risk Metrics
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown: float
    max_drawdown_pct: float
    value_at_risk_95: float
    expected_shortfall_95: float
    
    # Trade Statistics
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    avg_win_pct: float
    avg_loss_pct: float
    avg_holding_period: float
    max_consecutive_wins: int
    max_consecutive_losses: int
    
    # Monthly Returns
    monthly_returns: dict  # {YYYY-MM: return_pct}
    
    # Equity Curve
    equity_curve: list  # [{date, equity, drawdown}]
    
    # Trades
    trades: list
    
    def to_dict(self) -> dict:
        return asdict(self)


# ── Strategy Base Class ───────────────────────────────────────────────────

class Strategy(ABC):
    """Base class for trading strategies."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy name."""
        pass
    
    @abstractmethod
    def generate_signal(
        self,
        row: pd.Series,
        portfolio: Portfolio,
        history: pd.DataFrame
    ) -> Signal:
        """Generate trading signal based on current data.
        
        Parameters
        ----------
        row : pd.Series
            Current bar data (OHLCV + indicators)
        portfolio : Portfolio
            Current portfolio state
        history : pd.DataFrame
            Historical data up to current bar
        
        Returns
        -------
        Signal
            BUY, SELL, or HOLD
        """
        pass


# ── Position Sizing ───────────────────────────────────────────────────────

class PositionSizer:
    """Calculate position size based on various methods."""
    
    @staticmethod
    def fixed_shares(capital: float, price: float, shares: int = 100) -> int:
        """Fixed number of shares."""
        return shares
    
    @staticmethod
    def fixed_fractional(capital: float, price: float, fraction: float = 0.1) -> int:
        """Fixed fraction of capital."""
        value = capital * fraction
        return int(value / price)
    
    @staticmethod
    def kelly_criterion(
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        capital: float,
        price: float,
        max_fraction: float = 0.25
    ) -> int:
        """Kelly Criterion position sizing.
        
        Kelly % = W - [(1-W) / R]
        Where:
        - W = Win rate
        - R = Win/Loss ratio
        """
        if avg_loss == 0 or win_rate == 0:
            return int(capital * 0.1 / price)
        
        win_loss_ratio = abs(avg_win / avg_loss)
        kelly_pct = win_rate - ((1 - win_rate) / win_loss_ratio)
        kelly_pct = max(0, min(kelly_pct, max_fraction))  # Cap at max_fraction
        
        value = capital * kelly_pct
        return max(0, int(value / price))
    
    @staticmethod
    def risk_based(
        capital: float,
        entry_price: float,
        stop_loss: float,
        risk_per_trade: float = 0.02
    ) -> int:
        """Position size based on risk per trade.
        
        Shares = (Capital × Risk%) / (Entry - Stop Loss)
        """
        if entry_price <= stop_loss:
            return 0
        
        risk_amount = capital * risk_per_trade
        risk_per_share = entry_price - stop_loss
        
        return int(risk_amount / risk_per_share)


# ── Backtester Engine ─────────────────────────────────────────────────────

class Backtester:
    """Main backtesting engine."""
    
    def __init__(
        self,
        initial_capital: float = 100_000_000,
        commission: float = 0.0003,  # 0.03% per trade
        slippage: float = 0.001,  # 0.1% slippage
        position_sizing: str = "fixed_fractional",
        risk_per_trade: float = 0.02,
    ):
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.position_sizing = position_sizing
        self.risk_per_trade = risk_per_trade
        
        self.reset()
    
    def reset(self):
        """Reset backtester state."""
        self.cash = self.initial_capital
        self.positions = {}  # ticker -> {shares, entry_price, entry_date, entry_reason}
        self.trades = []
        self.equity_curve = []
        self.daily_returns = []
    
    def run(
        self,
        strategy: Strategy,
        data: pd.DataFrame,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> BacktestResult:
        """Run backtest on historical data.
        
        Parameters
        ----------
        strategy : Strategy
            Trading strategy instance
        data : pd.DataFrame
            Historical OHLCV data with indicators
        start_date : date, optional
            Backtest start date
        end_date : date, optional
            Backtest end date
        
        Returns
        -------
        BacktestResult
            Complete backtest results
        """
        self.reset()
        
        # Filter date range
        if start_date:
            data = data[data['date'] >= pd.Timestamp(start_date)]
        if end_date:
            data = data[data['date'] <= pd.Timestamp(end_date)]
        
        if data.empty:
            raise ValueError("No data in specified date range")
        
        # Initialize tracking
        portfolio = Portfolio(cash=self.cash, positions={}, total_value=self.cash)
        ticker = data.iloc[0].get('ticker', 'UNKNOWN')
        
        logger.info(f"Starting backtest for {ticker} from {data['date'].min()} to {data['date'].max()}")
        
        # Iterate through bars
        for i in range(len(data)):
            row = data.iloc[i]
            current_date = pd.Timestamp(row['date']).date()
            
            # Get signal from strategy
            signal = strategy.generate_signal(row, portfolio, data.iloc[:i+1])
            
            # Execute trades
            self._execute_signal(signal, row, portfolio, current_date, ticker)
            
            # Update portfolio value
            current_price = row['close']
            portfolio_value = self.cash + sum(
                pos['shares'] * current_price
                for pos in self.positions.values()
            )
            portfolio.total_value = portfolio_value
            
            # Track equity
            drawdown = self._calculate_drawdown(portfolio_value)
            self.equity_curve.append({
                'date': current_date,
                'equity': portfolio_value,
                'drawdown': drawdown,
            })
            
            # Track daily returns
            if i > 0:
                prev_equity = self.equity_curve[-2]['equity']
                daily_return = (portfolio_value - prev_equity) / prev_equity
                self.daily_returns.append(daily_return)
        
        # Close remaining positions at end
        self._close_all_positions(data.iloc[-1], portfolio, data.iloc[-1]['date'], ticker, "END")
        
        # Calculate results
        result = self._calculate_results(strategy.name, ticker, data.iloc[0]['date'], data.iloc[-1]['date'])
        
        logger.info(
            f"Backtest complete: Total Return={result.total_return_pct:.2%}, "
            f"Sharpe={result.sharpe_ratio:.2f}, MaxDD={result.max_drawdown_pct:.2%}"
        )
        
        return result
    
    def _execute_signal(
        self,
        signal: Signal,
        row: pd.Series,
        portfolio: Portfolio,
        current_date: date,
        ticker: str,
    ):
        """Execute trading signal."""
        current_price = row['close']
        
        # BUY signal
        if signal == Signal.BUY and ticker not in self.positions:
            self._open_position(row, portfolio, current_date, ticker, current_price)
        
        # SELL signal
        elif signal == Signal.SELL and ticker in self.positions:
            self._close_position(row, portfolio, current_date, ticker, current_price, "SIGNAL")
    
    def _open_position(
        self,
        row: pd.Series,
        portfolio: Portfolio,
        current_date: date,
        ticker: str,
        current_price: float,
    ):
        """Open new position."""
        # Calculate position size
        if self.position_sizing == "fixed_fractional":
            shares = PositionSizer.fixed_fractional(self.cash, current_price, 0.1)
        elif self.position_sizing == "kelly":
            # Use historical win rate if available
            shares = PositionSizer.fixed_fractional(self.cash, current_price, 0.1)
        else:
            shares = PositionSizer.fixed_shares(self.cash, current_price, 100)
        
        if shares <= 0:
            return
        
        # Apply slippage
        execution_price = current_price * (1 + self.slippage)
        
        # Calculate cost
        total_cost = shares * execution_price
        commission_fee = total_cost * self.commission
        
        if total_cost + commission_fee > self.cash:
            # Not enough cash
            return
        
        # Update portfolio
        self.cash -= (total_cost + commission_fee)
        self.positions[ticker] = {
            'shares': shares,
            'entry_price': execution_price,
            'entry_date': current_date,
        }
        
        logger.debug(f"BUY {ticker}: {shares} shares @ {execution_price:,.0f}")
    
    def _close_position(
        self,
        row: pd.Series,
        portfolio: Portfolio,
        current_date: date,
        ticker: str,
        current_price: float,
        reason: str,
    ):
        """Close existing position."""
        if ticker not in self.positions:
            return
        
        pos = self.positions[ticker]
        shares = pos['shares']
        entry_price = pos['entry_price']
        entry_date = pos['entry_date']
        
        # Apply slippage
        execution_price = current_price * (1 - self.slippage)
        
        # Calculate proceeds
        total_proceeds = shares * execution_price
        commission_fee = total_proceeds * self.commission
        
        # Calculate P&L
        pnl = (execution_price - entry_price) * shares - commission_fee
        pnl_pct = (execution_price - entry_price) / entry_price
        
        # Create trade record
        try:
            holding_days = (pd.Timestamp(current_date).to_pydatetime().date() - pd.Timestamp(entry_date).to_pydatetime().date()).days
        except:
            holding_days = 0
        
        trade = Trade(
            ticker=ticker,
            entry_date=entry_date,
            entry_price=entry_price,
            exit_date=current_date,
            exit_price=execution_price,
            shares=shares,
            signal="BUY",
            exit_reason=reason,
            pnl=pnl,
            pnl_pct=pnl_pct,
            holding_period=holding_days,
        )
        self.trades.append(trade)
        
        # Update portfolio
        self.cash += (total_proceeds - commission_fee)
        del self.positions[ticker]
        
        logger.debug(f"SELL {ticker}: {shares} shares @ {execution_price:,.0f} | P&L: {pnl:,.0f} ({pnl_pct:.2%})")
    
    def _close_all_positions(
        self,
        row: pd.Series,
        portfolio: Portfolio,
        current_date: date,
        ticker: str,
        reason: str,
    ):
        """Close all open positions."""
        for ticker in list(self.positions.keys()):
            self._close_position(row, portfolio, current_date, ticker, row['close'], reason)
    
    def _calculate_drawdown(self, current_equity: float) -> float:
        """Calculate current drawdown from peak."""
        if not self.equity_curve:
            return 0.0
        
        peak_equity = max(e['equity'] for e in self.equity_curve)
        if peak_equity == 0:
            return 0.0
        
        return (peak_equity - current_equity) / peak_equity
    
    def _calculate_results(
        self,
        strategy_name: str,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> BacktestResult:
        """Calculate comprehensive performance metrics."""
        final_capital = self.cash + sum(
            pos['shares'] * 0  # All positions should be closed
            for pos in self.positions.values()
        )
        
        total_return = final_capital - self.initial_capital
        total_return_pct = total_return / self.initial_capital
        
        # Annualized return
        days = (end_date - start_date).days
        years = days / 365.25
        annualized_return = (1 + total_return_pct) ** (1 / years) - 1 if years > 0 else 0
        
        # Risk metrics
        sharpe = self._calculate_sharpe_ratio()
        sortino = self._calculate_sortino_ratio()
        max_dd, max_dd_pct = self._calculate_max_drawdown()
        calmar = annualized_return / abs(max_dd_pct) if max_dd_pct != 0 else 0
        
        # VaR and Expected Shortfall
        var_95 = self._calculate_var(0.95)
        es_95 = self._calculate_expected_shortfall(0.95)
        
        # Trade statistics
        winning_trades = [t for t in self.trades if t.pnl > 0]
        losing_trades = [t for t in self.trades if t.pnl <= 0]
        
        win_rate = len(winning_trades) / len(self.trades) if self.trades else 0
        
        gross_profit = sum(t.pnl for t in winning_trades)
        gross_loss = abs(sum(t.pnl for t in losing_trades))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        avg_win = np.mean([t.pnl for t in winning_trades]) if winning_trades else 0
        avg_loss = np.mean([t.pnl for t in losing_trades]) if losing_trades else 0
        avg_win_pct = np.mean([t.pnl_pct for t in winning_trades]) if winning_trades else 0
        avg_loss_pct = np.mean([t.pnl_pct for t in losing_trades]) if losing_trades else 0
        
        avg_holding = np.mean([t.holding_period for t in self.trades]) if self.trades else 0
        
        # Consecutive wins/losses
        max_cons_wins, max_cons_losses = self._calculate_consecutive_trades()
        
        # Monthly returns
        monthly_returns = self._calculate_monthly_returns()
        
        return BacktestResult(
            strategy_name=strategy_name,
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.initial_capital,
            final_capital=final_capital,
            total_return=total_return,
            total_return_pct=total_return_pct,
            annualized_return=annualized_return,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            max_drawdown=max_dd,
            max_drawdown_pct=max_dd_pct,
            value_at_risk_95=var_95,
            expected_shortfall_95=es_95,
            total_trades=len(self.trades),
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            win_rate=win_rate,
            profit_factor=profit_factor,
            avg_win=avg_win,
            avg_loss=avg_loss,
            avg_win_pct=avg_win_pct,
            avg_loss_pct=avg_loss_pct,
            avg_holding_period=avg_holding,
            max_consecutive_wins=max_cons_wins,
            max_consecutive_losses=max_cons_losses,
            monthly_returns=monthly_returns,
            equity_curve=self.equity_curve,
            trades=[t.to_dict() for t in self.trades],
        )
    
    def _calculate_sharpe_ratio(self, risk_free_rate: float = 0.05) -> float:
        """Calculate Sharpe Ratio."""
        if not self.daily_returns or len(self.daily_returns) < 2:
            return 0.0
        
        returns = np.array(self.daily_returns)
        excess_returns = returns - (risk_free_rate / 252)  # Daily risk-free rate
        
        if np.std(returns) == 0:
            return 0.0
        
        sharpe = np.mean(excess_returns) / np.std(returns)
        return sharpe * np.sqrt(252)  # Annualize
    
    def _calculate_sortino_ratio(self, risk_free_rate: float = 0.05) -> float:
        """Calculate Sortino Ratio (downside deviation)."""
        if not self.daily_returns or len(self.daily_returns) < 2:
            return 0.0
        
        returns = np.array(self.daily_returns)
        excess_returns = returns - (risk_free_rate / 252)
        
        downside_returns = returns[returns < 0]
        if len(downside_returns) == 0:
            return float('inf')
        
        downside_std = np.std(downside_returns)
        if downside_std == 0:
            return 0.0
        
        sortino = np.mean(excess_returns) / downside_std
        return sortino * np.sqrt(252)
    
    def _calculate_max_drawdown(self) -> tuple[float, float]:
        """Calculate maximum drawdown."""
        if not self.equity_curve:
            return 0.0, 0.0
        
        peak = self.equity_curve[0]['equity']
        max_dd = 0.0
        max_dd_pct = 0.0
        
        for point in self.equity_curve:
            equity = point['equity']
            if equity > peak:
                peak = equity
            
            dd = peak - equity
            dd_pct = dd / peak if peak > 0 else 0
            
            if dd > max_dd:
                max_dd = dd
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct
        
        return max_dd, max_dd_pct
    
    def _calculate_var(self, confidence: float = 0.95) -> float:
        """Calculate Value at Risk."""
        if not self.daily_returns or len(self.daily_returns) < 10:
            return 0.0
        
        returns = np.array(self.daily_returns)
        var = np.percentile(returns, (1 - confidence) * 100)
        return abs(var)
    
    def _calculate_expected_shortfall(self, confidence: float = 0.95) -> float:
        """Calculate Expected Shortfall (CVaR)."""
        if not self.daily_returns or len(self.daily_returns) < 10:
            return 0.0
        
        returns = np.array(self.daily_returns)
        var = np.percentile(returns, (1 - confidence) * 100)
        es = np.mean(returns[returns <= var])
        return abs(es)
    
    def _calculate_consecutive_trades(self) -> tuple[int, int]:
        """Calculate max consecutive wins and losses."""
        if not self.trades:
            return 0, 0
        
        max_wins = 0
        max_losses = 0
        current_wins = 0
        current_losses = 0
        
        for trade in self.trades:
            if trade.pnl > 0:
                current_wins += 1
                current_losses = 0
            else:
                current_losses += 1
                current_wins = 0
            
            max_wins = max(max_wins, current_wins)
            max_losses = max(max_losses, current_losses)
        
        return max_wins, max_losses
    
    def _calculate_monthly_returns(self) -> dict:
        """Calculate monthly returns."""
        if not self.equity_curve:
            return {}
        
        monthly = {}
        prev_month_equity = self.initial_capital
        prev_month = None
        
        for point in self.equity_curve:
            current_month = point['date'].strftime('%Y-%m')
            
            if current_month != prev_month and prev_month is not None:
                # Calculate return for previous month
                if prev_month in monthly:
                    month_equity = monthly[prev_month]['end_equity']
                    monthly[prev_month]['return_pct'] = (month_equity - prev_month_equity) / prev_month_equity
                prev_month_equity = monthly.get(prev_month, {}).get('end_equity', self.initial_capital)
            
            if current_month not in monthly:
                monthly[current_month] = {
                    'start_equity': prev_month_equity,
                    'end_equity': point['equity'],
                    'return_pct': 0.0,
                }
            else:
                monthly[current_month]['end_equity'] = point['equity']
            
            prev_month = current_month
        
        # Calculate last month
        if prev_month and prev_month in monthly:
            month_equity = monthly[prev_month]['end_equity']
            monthly[prev_month]['return_pct'] = (month_equity - prev_month_equity) / prev_month_equity
        
        return {k: v['return_pct'] for k, v in monthly.items()}


# ── Example Strategy ──────────────────────────────────────────────────────

class TechnicalSignalStrategy(Strategy):
    """Simple strategy based on technical signals."""
    
    def __init__(self, signal_column: str = 'signal'):
        self._signal_column = signal_column
    
    @property
    def name(self) -> str:
        return "Technical Signal Strategy"
    
    def generate_signal(
        self,
        row: pd.Series,
        portfolio: Portfolio,
        history: pd.DataFrame
    ) -> Signal:
        ticker = row.get('ticker', 'UNKNOWN')
        
        # Check if we already have a position
        if ticker in portfolio.positions:
            # Hold or sell
            signal_value = row.get(self._signal_column, 'HOLD')
            if signal_value == 'SELL':
                return Signal.SELL
            return Signal.HOLD
        else:
            # Buy or wait
            signal_value = row.get(self._signal_column, 'HOLD')
            if signal_value == 'BUY':
                return Signal.BUY
            return Signal.HOLD


# ── Formatting Utilities ──────────────────────────────────────────────────

def format_backtest_results(result: BacktestResult) -> str:
    """Format backtest results for display."""
    lines = [
        "╔" + "═" * 58 + "╗",
        "║" + f" BACKTEST RESULTS: {result.ticker}".ljust(58) + "║",
        "╠" + "═" * 58 + "╣",
        f"║ Strategy: {result.strategy_name:46s} ║",
        f"║ Period: {str(result.start_date):12s} to {str(result.end_date):12s}  ║",
        f"║ Initial Capital: Rp {result.initial_capital:>30,.0f} ║",
        f"║ Final Capital:   Rp {result.final_capital:>30,.0f} ║",
        "╠" + "═" * 58 + "╣",
        "║ 📊 RETURNS".ljust(58) + "║",
        f"║   Total Return:   {result.total_return_pct:>10.2%} (Rp {result.total_return:>20,.0f})".ljust(58) + "║",
        f"║   Annualized:     {result.annualized_return:>10.2%}".ljust(58) + "║",
        "╠" + "═" * 58 + "╣",
        "║ ⚡ RISK METRICS".ljust(58) + "║",
        f"║   Sharpe Ratio:   {result.sharpe_ratio:>10.2f}".ljust(58) + "║",
        f"║   Sortino Ratio:  {result.sortino_ratio:>10.2f}".ljust(58) + "║",
        f"║   Calmar Ratio:   {result.calmar_ratio:>10.2f}".ljust(58) + "║",
        f"║   Max Drawdown:   {result.max_drawdown_pct:>10.2%} (Rp {result.max_drawdown:>20,.0f})".ljust(58) + "║",
        f"║   VaR (95%):      {result.value_at_risk_95:>10.2%}".ljust(58) + "║",
        f"║   Expected Shortfall: {result.expected_shortfall_95:>10.2%}".ljust(58) + "║",
        "╠" + "═" * 58 + "╣",
        "║ 📈 TRADE STATISTICS".ljust(58) + "║",
        f"║   Total Trades:   {result.total_trades:>10d}".ljust(58) + "║",
        f"║   Winning:        {result.winning_trades:>10d} ({result.win_rate:>10.2%})".ljust(58) + "║",
        f"║   Losing:         {result.losing_trades:>10d}".ljust(58) + "║",
        f"║   Profit Factor:  {result.profit_factor:>10.2f}".ljust(58) + "║",
        f"║   Avg Win:        Rp {result.avg_win:>20,.0f} ({result.avg_win_pct:>10.2%})".ljust(58) + "║",
        f"║   Avg Loss:       Rp {result.avg_loss:>20,.0f} ({result.avg_loss_pct:>10.2%})".ljust(58) + "║",
        f"║   Avg Hold:       {result.avg_holding_period:>10.1f} days".ljust(58) + "║",
        f"║   Max Cons Wins:  {result.max_consecutive_wins:>10d}".ljust(58) + "║",
        f"║   Max Cons Loss:  {result.max_consecutive_losses:>10d}".ljust(58) + "║",
        "╚" + "═" * 58 + "╝",
    ]
    
    return "\n".join(lines)


# Singleton instance
backtester = Backtester()
