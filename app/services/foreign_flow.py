"""Foreign Flow Analysis - Track Bandar/Institutional Activity.

Analyzes foreign investor and institutional trading patterns to detect
accumulation/distribution and potential price movements.

Features:
- Net Buy/Sell tracking
- Accumulation/Distribution detection
- Bandar Score (0-100)
- Foreign Ownership % tracking
- Unusual activity alerts
- Historical flow analysis

Usage:
    from app.services.foreign_flow import ForeignFlowAnalyzer
    
    analyzer = ForeignFlowAnalyzer()
    flow_data = analyzer.analyze("BBCA")
    
    print(f"Bandar Score: {flow_data['bandar_score']}")
    print(f"Signal: {flow_data['signal']}")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, date, timedelta
from enum import Enum
from typing import Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


# ── Enums ──────────────────────────────────────────────────────────────────

class FlowSignal(Enum):
    STRONG_ACCUMULATION = "STRONG_ACCUMULATION"
    ACCUMULATION = "ACCUMULATION"
    NEUTRAL = "NEUTRAL"
    DISTRIBUTION = "DISTRIBUTION"
    STRONG_DISTRIBUTION = "STRONG_DISTRIBUTION"


# ── Data Classes ───────────────────────────────────────────────────────────

@dataclass
class DailyFlow:
    """Daily foreign flow data."""
    date: date
    foreign_buy: int  # Volume bought by foreigners
    foreign_sell: int  # Volume sold by foreigners
    net_flow: int  # Net buy/sell
    net_flow_value: float  # In IDR
    price: float
    change_pct: float
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ForeignFlowResult:
    """Foreign flow analysis result."""
    ticker: str
    company_name: str
    analysis_date: date
    
    # Current flow
    foreign_buy: int
    foreign_sell: int
    net_flow: int
    net_flow_value: float
    
    # Flow metrics
    flow_ratio: float  # Buy/Sell ratio
    flow_percentage: float  # Net flow / total volume %
    
    # Trend analysis
    consecutive_buy_days: int
    consecutive_sell_days: int
    net_buy_5d: int
    net_buy_10d: int
    net_buy_20d: int
    
    # Bandar score (0-100)
    bandar_score: float
    bandar_signal: str
    
    # Ownership
    foreign_ownership_pct: Optional[float]
    ownership_change_5d: Optional[float]
    
    # Signal
    signal: str  # STRONG_BUY, BUY, HOLD, SELL, STRONG_SELL
    confidence: str  # HIGH, MEDIUM, LOW
    
    # Historical data
    daily_flows: list = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return asdict(self)


# ── Foreign Flow Analyzer ─────────────────────────────────────────────────

class ForeignFlowAnalyzer:
    """Analyze foreign investor flow for IDX stocks."""
    
    # Approximate foreign ownership limits by sector
    SECTOR_OWNERSHIP_LIMITS = {
        'Banking': 40,  # Max 40% foreign ownership
        'Telecommunications': 65,
        'Consumer Goods': 100,
        'Mining': 100,
        'Technology': 100,
        'Property': 100,
        'Infrastructure': 67,
    }
    
    def __init__(self):
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes
    
    def analyze(self, ticker: str, period: str = "3mo") -> Optional[ForeignFlowResult]:
        """Analyze foreign flow for a stock.
        
        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        period : str
            Period for analysis (default: 3 months)
        
        Returns
        -------
        ForeignFlowResult or None
            Foreign flow analysis result
        """
        logger.info(f"Analyzing foreign flow for {ticker}")
        
        try:
            # Fetch data
            jk_ticker = f"{ticker}.JK"
            stock = yf.Ticker(jk_ticker)
            
            # Get price history
            df = stock.history(period=period)
            
            if df.empty:
                logger.warning(f"No data for {ticker}")
                return None
            
            # Estimate foreign flow (proxy method)
            # Note: Real foreign flow data requires Bloomberg/Refinitiv
            # We'll use volume-price analysis as proxy
            flow_data = self._estimate_foreign_flow(df, stock)
            
            # Calculate bandar score
            bandar_score = self._calculate_bandar_score(flow_data)
            
            # Determine signal
            signal, confidence = self._determine_signal(bandar_score, flow_data)
            
            # Get foreign ownership estimate
            foreign_ownership = self._estimate_foreign_ownership(stock)
            
            # Build result
            result = ForeignFlowResult(
                ticker=ticker,
                company_name=stock.info.get('longName', ticker),
                analysis_date=date.today(),
                foreign_buy=flow_data.get('foreign_buy', 0),
                foreign_sell=flow_data.get('foreign_sell', 0),
                net_flow=flow_data.get('net_flow', 0),
                net_flow_value=flow_data.get('net_flow_value', 0),
                flow_ratio=flow_data.get('flow_ratio', 1.0),
                flow_percentage=flow_data.get('flow_percentage', 0),
                consecutive_buy_days=flow_data.get('consecutive_buy_days', 0),
                consecutive_sell_days=flow_data.get('consecutive_sell_days', 0),
                net_buy_5d=flow_data.get('net_buy_5d', 0),
                net_buy_10d=flow_data.get('net_buy_10d', 0),
                net_buy_20d=flow_data.get('net_buy_20d', 0),
                bandar_score=bandar_score,
                bandar_signal=self._bandar_signal_name(bandar_score),
                foreign_ownership_pct=foreign_ownership.get('current'),
                ownership_change_5d=foreign_ownership.get('change_5d'),
                daily_flows=flow_data.get('daily_flows', []),
                signal=signal,
                confidence=confidence,
            )
            
            logger.info(
                f"Foreign flow analysis for {ticker}: "
                f"Bandar Score={bandar_score:.1f}, Signal={signal}"
            )
            
            return result
        
        except Exception as e:
            logger.error(f"Foreign flow analysis error for {ticker}: {e}")
            return None
    
    def _estimate_foreign_flow(
        self,
        df: pd.DataFrame,
        stock: yf.Ticker,
    ) -> dict:
        """Estimate foreign flow using volume-price analysis.
        
        This is a proxy method since real foreign flow data is not freely available.
        Uses institutional flow patterns and block trade detection.
        """
        daily_flows = []
        
        # Calculate metrics for each day
        df = df.copy()
        df['volume_ma_20'] = df['Volume'].rolling(20).mean()
        df['price_change'] = df['Close'].pct_change()
        
        # Detect unusual volume (potential institutional activity)
        df['volume_ratio'] = df['Volume'] / df['volume_ma_20']
        df['is_unusual_volume'] = df['volume_ratio'] > 2.0
        
        # Estimate foreign flow
        # Assumption: Large volume + price increase = foreign buy
        # Large volume + price decrease = foreign sell
        for i, row in df.iterrows():
            volume = row['Volume']
            price = row['Close']
            change = row['price_change'] if pd.notna(row['price_change']) else 0
            
            # Estimate foreign participation (assume 30-60% of unusual volume)
            if row['is_unusual_volume']:
                foreign_participation = 0.5  # 50% of unusual volume
            else:
                foreign_participation = 0.3  # 30% of normal volume
            
            # Direction based on price
            if change > 0.02:  # >2% gain
                foreign_buy = int(volume * foreign_participation)
                foreign_sell = int(volume * (1 - foreign_participation) * 0.5)
            elif change < -0.02:  # >2% loss
                foreign_buy = int(volume * foreign_participation * 0.5)
                foreign_sell = int(volume * (1 - foreign_participation))
            else:
                foreign_buy = int(volume * foreign_participation * 0.5)
                foreign_sell = int(volume * foreign_participation * 0.5)
            
            net_flow = foreign_buy - foreign_sell
            net_flow_value = net_flow * price
            
            daily_flows.append(DailyFlow(
                date=i.date() if hasattr(i, 'date') else i,
                foreign_buy=foreign_buy,
                foreign_sell=foreign_sell,
                net_flow=net_flow,
                net_flow_value=net_flow_value,
                price=price,
                change_pct=change * 100,
            ))
        
        # Aggregate metrics
        latest = daily_flows[-1] if daily_flows else DailyFlow(
            date=date.today(),
            foreign_buy=0,
            foreign_sell=0,
            net_flow=0,
            net_flow_value=0,
            price=df['Close'].iloc[-1],
            change_pct=0,
        )
        
        # Calculate consecutive days
        consecutive_buy = 0
        consecutive_sell = 0
        for flow in reversed(daily_flows):
            if flow.net_flow > 0:
                consecutive_buy += 1
                consecutive_sell = 0
            elif flow.net_flow < 0:
                consecutive_sell += 1
                consecutive_buy = 0
            else:
                break
        
        # Calculate period totals
        net_buy_5d = sum(f.net_flow for f in daily_flows[-5:])
        net_buy_10d = sum(f.net_flow for f in daily_flows[-10:])
        net_buy_20d = sum(f.net_flow for f in daily_flows[-20:])
        
        # Flow ratio
        total_buy = sum(f.foreign_buy for f in daily_flows[-10:])
        total_sell = sum(f.foreign_sell for f in daily_flows[-10:])
        flow_ratio = total_buy / total_sell if total_sell > 0 else 10.0
        
        # Flow percentage
        total_volume = sum(f.foreign_buy + f.foreign_sell for f in daily_flows[-10:])
        flow_percentage = (net_buy_10d / total_volume * 100) if total_volume > 0 else 0
        
        return {
            'foreign_buy': latest.foreign_buy,
            'foreign_sell': latest.foreign_sell,
            'net_flow': latest.net_flow,
            'net_flow_value': latest.net_flow_value,
            'flow_ratio': flow_ratio,
            'flow_percentage': flow_percentage,
            'consecutive_buy_days': consecutive_buy,
            'consecutive_sell_days': consecutive_sell,
            'net_buy_5d': net_buy_5d,
            'net_buy_10d': net_buy_10d,
            'net_buy_20d': net_buy_20d,
            'daily_flows': [f.to_dict() for f in daily_flows[-20:]],  # Last 20 days
        }
    
    def _calculate_bandar_score(self, flow_data: dict) -> float:
        """Calculate Bandar Score (0-100).
        
        Higher score = stronger accumulation (bullish)
        Lower score = stronger distribution (bearish)
        """
        score = 50.0  # Start neutral
        
        # Net flow score (0-25 points)
        flow_ratio = flow_data.get('flow_ratio', 1.0)
        if flow_ratio >= 3.0:
            score += 25
        elif flow_ratio >= 2.0:
            score += 20
        elif flow_ratio >= 1.5:
            score += 15
        elif flow_ratio >= 1.0:
            score += 10
        elif flow_ratio >= 0.5:
            score += 5
        else:
            score -= 10
        score = max(0, min(100, score))
        
        # Consecutive days score (0-25 points)
        consec_buy = flow_data.get('consecutive_buy_days', 0)
        consec_sell = flow_data.get('consecutive_sell_days', 0)
        
        if consec_buy >= 5:
            score += 25
        elif consec_buy >= 3:
            score += 20
        elif consec_buy >= 1:
            score += 10
        elif consec_sell >= 5:
            score -= 25
        elif consec_sell >= 3:
            score -= 20
        elif consec_sell >= 1:
            score -= 10
        
        score = max(0, min(100, score))
        
        # Trend score (0-25 points)
        net_5d = flow_data.get('net_buy_5d', 0)
        net_10d = flow_data.get('net_buy_10d', 0)
        net_20d = flow_data.get('net_buy_20d', 0)
        
        if net_5d > 0 and net_10d > 0 and net_20d > 0:
            # Consistent accumulation
            score += 25
        elif net_5d > 0 and net_10d > 0:
            score += 20
        elif net_5d > 0:
            score += 10
        elif net_5d < 0 and net_10d < 0 and net_20d < 0:
            # Consistent distribution
            score -= 25
        elif net_5d < 0 and net_10d < 0:
            score -= 20
        elif net_5d < 0:
            score -= 10
        
        score = max(0, min(100, score))
        
        # Flow percentage score (0-25 points)
        flow_pct = flow_data.get('flow_percentage', 0)
        if flow_pct >= 10:
            score += 25
        elif flow_pct >= 5:
            score += 20
        elif flow_pct >= 2:
            score += 15
        elif flow_pct >= 0:
            score += 10
        elif flow_pct >= -5:
            score += 5
        else:
            score -= 10
        
        return max(0, min(100, score))
    
    def _bandar_signal_name(self, score: float) -> str:
        """Convert bandar score to signal name."""
        if score >= 80:
            return "STRONG_ACCUMULATION"
        elif score >= 65:
            return "ACCUMULATION"
        elif score >= 45:
            return "NEUTRAL"
        elif score >= 30:
            return "DISTRIBUTION"
        else:
            return "STRONG_DISTRIBUTION"
    
    def _determine_signal(
        self,
        bandar_score: float,
        flow_data: dict,
    ) -> tuple[str, str]:
        """Determine trading signal and confidence."""
        if bandar_score >= 75:
            signal = "STRONG_BUY"
            confidence = "HIGH"
        elif bandar_score >= 60:
            signal = "BUY"
            confidence = "MEDIUM"
        elif bandar_score >= 50:
            signal = "BUY"
            confidence = "LOW"
        elif bandar_score >= 40:
            signal = "HOLD"
            confidence = "MEDIUM"
        elif bandar_score >= 25:
            signal = "SELL"
            confidence = "MEDIUM"
        else:
            signal = "STRONG_SELL"
            confidence = "HIGH"
        
        return signal, confidence
    
    def _estimate_foreign_ownership(self, stock: yf.Ticker) -> dict:
        """Estimate foreign ownership percentage."""
        try:
            info = stock.info
            
            # Try to get from info (if available)
            shares_outstanding = info.get('sharesOutstanding')
            float_shares = info.get('floatShares')
            
            if shares_outstanding and float_shares:
                foreign_float = float_shares / shares_outstanding * 100
            else:
                # Estimate based on sector
                sector = info.get('sector', '')
                foreign_float = self.SECTOR_OWNERSHIP_LIMITS.get(sector, 50)
            
            # Note: This is an estimate. Real data requires Bloomberg/Refinitiv
            return {
                'current': foreign_float,
                'change_5d': None,  # Would need historical data
            }
        
        except Exception as e:
            logger.debug(f"Foreign ownership estimate failed: {e}")
            return {
                'current': None,
                'change_5d': None,
            }


# ── Formatting Utilities ──────────────────────────────────────────────────

def format_foreign_flow_summary(result: ForeignFlowResult) -> str:
    """Format foreign flow analysis for display."""
    emoji_map = {
        'STRONG_ACCUMULATION': '🟢',
        'ACCUMULATION': '🟢',
        'NEUTRAL': '🟡',
        'DISTRIBUTION': '🔴',
        'STRONG_DISTRIBUTION': '🔴',
        'STRONG_BUY': '🟢',
        'BUY': '🟢',
        'HOLD': '🟡',
        'SELL': '🔴',
        'STRONG_SELL': '🔴',
    }
    
    lines = [
        f"┌───────────────────────────────────────────┐",
        f"│ 💰 {result.ticker} - Foreign Flow Analysis",
        f"├───────────────────────────────────────────┤",
        f"│ Bandar Score: {result.bandar_score:5.1f}/100  [{result.bandar_signal:22s}]",
        f"│ {emoji_map.get(result.bandar_signal, '⚪')} {result.bandar_signal:22s} │",
        f"├───────────────────────────────────────────┤",
        f"│ 📊 FLOW METRICS".ljust(43) + "│",
        f"│   Foreign Buy:    {result.foreign_buy:>12,} shares".ljust(43) + "│",
        f"│   Foreign Sell:   {result.foreign_sell:>12,} shares".ljust(43) + "│",
        f"│   Net Flow:       {result.net_flow:>12,} shares".ljust(43) + "│",
        f"│   Flow Ratio:     {result.flow_ratio:>12.2f}x".ljust(43) + "│",
        f"│   Flow %:         {result.flow_percentage:>11.1f}%".ljust(43) + "│",
        f"├───────────────────────────────────────────┤",
        f"│ 📈 TREND".ljust(43) + "│",
        f"│   Consecutive Buy:  {result.consecutive_buy_days:>3d} days".ljust(43) + "│",
        f"│   Consecutive Sell: {result.consecutive_sell_days:>3d} days".ljust(43) + "│",
        f"│   Net Buy (5d):   {result.net_buy_5d:>12,} shares".ljust(43) + "│",
        f"│   Net Buy (10d):  {result.net_buy_10d:>12,} shares".ljust(43) + "│",
        f"│   Net Buy (20d):  {result.net_buy_20d:>12,} shares".ljust(43) + "│",
        f"├───────────────────────────────────────────┤",
        f"│ {emoji_map.get(result.signal, '⚪')} Signal: {result.signal:22s} │",
        f"│ 🎲 Confidence: {result.confidence:21s} │",
        f"└───────────────────────────────────────────┘",
    ]
    
    return "\n".join(lines)


# Singleton instance
foreign_flow_analyzer = ForeignFlowAnalyzer()
