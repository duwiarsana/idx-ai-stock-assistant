"""Combined Analysis Engine - Technical + Fundamental.

Integrates technical analysis with fundamental analysis for comprehensive
stock evaluation and better investment decisions.

Features:
- Combined scoring (Technical + Fundamental)
- Sector-relative valuation
- Quality-at-reasonable-price (QARP) scoring
- Growth-at-reasonable-price (GARP) scoring
- Value investing scoring

Usage:
    from app.services.combined_analyzer import CombinedAnalyzer
    
    analyzer = CombinedAnalyzer()
    result = analyzer.analyze("BBCA")
    
    print(f"Combined Score: {result.combined_score}")
    print(f"Technical Score: {result.technical_score}")
    print(f"Fundamental Score: {result.fundamental_score}")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import date
from enum import Enum
from typing import Optional

import pandas as pd

from app.services.enhanced_technicals import (
    EnhancedTechnicalEngine,
    TechnicalAnalysisResult,
)
from app.services.fundamental_analyzer import (
    FundamentalAnalyzer,
    FundamentalResult,
)

logger = logging.getLogger(__name__)


# ── Enums ──────────────────────────────────────────────────────────────────

class InvestmentStyle(Enum):
    VALUE = "VALUE"  # Low PE, Low PB, High Dividend
    GROWTH = "GROWTH"  # High Revenue Growth, High EPS Growth
    GARP = "GARP"  # Growth At Reasonable Price
    QUALITY = "QUALITY"  # High ROE, High Margin, Low Debt
    MOMENTUM = "MOMENTUM"  # Strong Price Momentum


# ── Data Classes ───────────────────────────────────────────────────────────

@dataclass
class CombinedAnalysisResult:
    """Combined technical + fundamental analysis result."""
    ticker: str
    company_name: str
    sector: str
    
    # Individual scores (0-100)
    technical_score: float
    fundamental_score: float
    combined_score: float
    
    # Investment style scores
    value_score: float = 0.0
    growth_score: float = 0.0
    quality_score: float = 0.0
    momentum_score: float = 0.0
    
    # Signals
    technical_signal: str = "HOLD"  # BUY, SELL, HOLD
    fundamental_grade: str = "HOLD"  # STRONG_BUY, BUY, HOLD, SELL, STRONG_SELL
    combined_signal: str = "HOLD"
    
    # Confidence
    confidence: str = "MEDIUM"  # HIGH, MEDIUM, LOW
    conviction: float = 0.0  # 0.0 - 1.0
    
    # Details
    technical_result: Optional[TechnicalAnalysisResult] = None
    fundamental_result: Optional[FundamentalResult] = None
    
    # Metadata
    analysis_date: date = field(default_factory=date.today)
    
    def to_dict(self) -> dict:
        return asdict(self)


# ── Combined Analyzer ─────────────────────────────────────────────────────

class CombinedAnalyzer:
    """Combine technical and fundamental analysis."""
    
    # Weights for combined score based on investment horizon
    HORIZON_WEIGHTS = {
        'short': {'technical': 0.70, 'fundamental': 0.30},  # Swing trading
        'medium': {'technical': 0.50, 'fundamental': 0.50},  # Position trading
        'long': {'technical': 0.30, 'fundamental': 0.70},  # Investing
    }
    
    def __init__(self, investment_horizon: str = "medium"):
        self.technical_engine = EnhancedTechnicalEngine()
        self.fundamental_analyzer = FundamentalAnalyzer()
        self.investment_horizon = investment_horizon
        self.weights = self.HORIZON_WEIGHTS.get(investment_horizon, self.HORIZON_WEIGHTS['medium'])
    
    def analyze(
        self,
        ticker: str,
        price_data: Optional[pd.DataFrame] = None,
    ) -> Optional[CombinedAnalysisResult]:
        """Run combined technical + fundamental analysis.
        
        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        price_data : pd.DataFrame, optional
            Historical price data for technical analysis
        
        Returns
        -------
        CombinedAnalysisResult or None if analysis fails
        """
        logger.info(f"Starting combined analysis for {ticker}")
        
        try:
            # Run fundamental analysis
            fundamental_result = self.fundamental_analyzer.analyze(ticker)
            if not fundamental_result:
                logger.warning(f"Fundamental analysis failed for {ticker}")
                return None
            
            # Run technical analysis if price data provided
            technical_result = None
            if price_data is not None and not price_data.empty:
                technical_result = self.technical_engine.analyze(price_data, ticker)
            
            # Calculate combined score
            fundamental_score = fundamental_result.overall_score
            technical_score = technical_result.composite_score if technical_result else 50.0
            
            combined_score = (
                technical_score * self.weights['technical'] +
                fundamental_score * self.weights['fundamental']
            )
            
            # Calculate investment style scores
            value_score = self._calculate_value_score(fundamental_result)
            growth_score = self._calculate_growth_score(fundamental_result)
            quality_score = self._calculate_quality_score(fundamental_result)
            momentum_score = self._calculate_momentum_score(technical_result)
            
            # Determine signals
            technical_signal = technical_result.signal if technical_result else "HOLD"
            fundamental_grade = fundamental_result.investment_grade
            
            combined_signal = self._determine_combined_signal(
                technical_signal,
                fundamental_grade,
                combined_score
            )
            
            # Determine confidence
            confidence, conviction = self._determine_confidence(
                technical_result,
                fundamental_result,
                combined_score
            )
            
            # Build result
            result = CombinedAnalysisResult(
                ticker=ticker,
                company_name=fundamental_result.company_name,
                sector=fundamental_result.sector,
                technical_score=round(technical_score, 2),
                fundamental_score=round(fundamental_score, 2),
                combined_score=round(combined_score, 2),
                value_score=round(value_score, 2),
                growth_score=round(growth_score, 2),
                quality_score=round(quality_score, 2),
                momentum_score=round(momentum_score, 2),
                technical_signal=technical_signal,
                fundamental_grade=fundamental_grade,
                combined_signal=combined_signal,
                confidence=confidence,
                conviction=round(conviction, 2),
                technical_result=technical_result,
                fundamental_result=fundamental_result,
            )
            
            logger.info(
                f"Combined analysis complete for {ticker}: "
                f"Score={combined_score:.1f}, Signal={combined_signal}"
            )
            
            return result
        
        except Exception as e:
            logger.error(f"Combined analysis error for {ticker}: {e}")
            return None
    
    def _calculate_value_score(self, fundamental: FundamentalResult) -> float:
        """Calculate value investing score (0-100)."""
        score = 0.0
        factors = 0
        
        ratios = fundamental.ratios
        
        # Low PE (0-25 points)
        if ratios.pe_ratio and ratios.pe_ratio > 0:
            if ratios.pe_ratio < 10:
                score += 25
            elif ratios.pe_ratio < 15:
                score += 20
            elif ratios.pe_ratio < 20:
                score += 15
            else:
                score += 5
            factors += 25
        
        # Low PB (0-25 points)
        if ratios.pb_ratio and ratios.pb_ratio > 0:
            if ratios.pb_ratio < 1:
                score += 25  # Below book value
            elif ratios.pb_ratio < 2:
                score += 20
            elif ratios.pb_ratio < 3:
                score += 15
            else:
                score += 5
            factors += 25
        
        # High Dividend Yield (0-25 points)
        if fundamental.ratios and hasattr(fundamental.ratios, 'dividend_yield'):
            div_yield = getattr(fundamental.ratios, 'dividend_yield', 0)
            if div_yield and div_yield > 0:
                if div_yield > 0.05:
                    score += 25
                elif div_yield > 0.03:
                    score += 20
                elif div_yield > 0.02:
                    score += 15
                else:
                    score += 5
                factors += 25
        
        # Low Debt (0-25 points)
        if ratios.debt_to_equity is not None:
            if ratios.debt_to_equity < 0.5:
                score += 25
            elif ratios.debt_to_equity < 1:
                score += 20
            elif ratios.debt_to_equity < 2:
                score += 15
            else:
                score += 5
            factors += 25
        
        return (score / factors * 100) if factors > 0 else 50.0
    
    def _calculate_growth_score(self, fundamental: FundamentalResult) -> float:
        """Calculate growth investing score (0-100)."""
        return fundamental.growth_score  # Already calculated
    
    def _calculate_quality_score(self, fundamental: FundamentalResult) -> float:
        """Calculate quality investing score (0-100)."""
        score = 0.0
        factors = 0
        
        ratios = fundamental.ratios
        
        # High ROE (0-30 points)
        if ratios.roe is not None:
            roe = ratios.roe * 100
            if roe >= 20:
                score += 30
            elif roe >= 15:
                score += 25
            elif roe >= 10:
                score += 20
            elif roe >= 5:
                score += 10
            else:
                score += 5
            factors += 30
        
        # High Margin (0-25 points)
        if ratios.net_margin is not None:
            margin = ratios.net_margin * 100
            if margin >= 20:
                score += 25
            elif margin >= 15:
                score += 20
            elif margin >= 10:
                score += 15
            else:
                score += 5
            factors += 25
        
        # Low Debt (0-25 points)
        if ratios.debt_to_equity is not None:
            if ratios.debt_to_equity < 0.5:
                score += 25
            elif ratios.debt_to_equity < 1:
                score += 20
            elif ratios.debt_to_equity < 2:
                score += 10
            else:
                score += 5
            factors += 25
        
        # Stable Earnings (0-20 points) - simplified
        if fundamental.growth.earnings_growth_yoy is not None:
            if fundamental.growth.earnings_growth_yoy > 0:
                score += 20
            else:
                score += 5
            factors += 20
        
        return (score / factors * 100) if factors > 0 else 50.0
    
    def _calculate_momentum_score(self, technical: Optional[TechnicalAnalysisResult]) -> float:
        """Calculate momentum score (0-100)."""
        if not technical:
            return 50.0
        
        score = 0.0
        factors = 0
        
        # Trend strength (0-40 points)
        trend_map = {
            'STRONG_UPTREND': 40,
            'UPTREND': 30,
            'SIDEWAYS': 20,
            'DOWNTREND': 10,
            'STRONG_DOWNTREND': 0,
        }
        score += trend_map.get(technical.trend_direction, 20)
        factors += 40
        
        # Technical score (0-30 points)
        score += technical.composite_score * 0.3
        factors += 30
        
        # Volume confirmation (0-30 points)
        score += technical.volume_score * 0.3
        factors += 30
        
        return min(100, max(0, score))
    
    def _determine_combined_signal(
        self,
        technical_signal: str,
        fundamental_grade: str,
        combined_score: float
    ) -> str:
        """Determine combined trading signal."""
        # Both bullish
        if technical_signal == "BUY" and fundamental_grade in ["STRONG_BUY", "BUY"]:
            return "STRONG_BUY"
        
        # Both bearish
        if technical_signal == "SELL" and fundamental_grade in ["SELL", "STRONG_SELL"]:
            return "STRONG_SELL"
        
        # Strong fundamental, neutral technical
        if fundamental_grade == "STRONG_BUY" and technical_signal == "HOLD":
            return "BUY"
        
        # Strong technical, neutral fundamental
        if technical_signal == "BUY" and fundamental_grade == "HOLD":
            return "BUY"
        
        # High combined score
        if combined_score >= 75:
            return "BUY"
        elif combined_score >= 65:
            return "BUY"
        elif combined_score <= 35:
            return "SELL"
        elif combined_score <= 45:
            return "SELL"
        
        return "HOLD"
    
    def _determine_confidence(
        self,
        technical: Optional[TechnicalAnalysisResult],
        fundamental: Optional[FundamentalResult],
        combined_score: float
    ) -> tuple[str, float]:
        """Determine confidence level and conviction."""
        agreement_score = 0.0
        
        # Check if technical and fundamental agree
        if technical and fundamental:
            tech_bullish = technical.signal in ["BUY"]
            tech_bearish = technical.signal in ["SELL"]
            fund_bullish = fundamental.investment_grade in ["STRONG_BUY", "BUY"]
            fund_bearish = fundamental.investment_grade in ["SELL", "STRONG_SELL"]
            
            if (tech_bullish and fund_bullish) or (tech_bearish and fund_bearish):
                agreement_score = 1.0  # Full agreement
            elif technical.signal == "HOLD" or fundamental.investment_grade == "HOLD":
                agreement_score = 0.5  # Partial agreement
            else:
                agreement_score = 0.0  # Disagreement
        
        # Calculate conviction
        score_factor = abs(combined_score - 50) / 50  # 0-1 based on distance from 50
        conviction = (agreement_score * 0.6 + score_factor * 0.4)
        
        # Determine confidence level
        if conviction >= 0.8:
            return "HIGH", conviction
        elif conviction >= 0.5:
            return "MEDIUM", conviction
        else:
            return "LOW", conviction


# ── Formatting Utilities ──────────────────────────────────────────────────

def format_combined_summary(result: CombinedAnalysisResult) -> str:
    """Format combined analysis for display."""
    emoji_map = {
        'STRONG_BUY': '🟢',
        'BUY': '🟢',
        'HOLD': '🟡',
        'SELL': '🔴',
        'STRONG_SELL': '🔴',
        'HIGH': '🟢',
        'MEDIUM': '🟡',
        'LOW': '🔴',
    }
    
    lines = [
        f"┌───────────────────────────────────────────┐",
        f"│ 🎯 {result.ticker} - Combined Analysis",
        f"├───────────────────────────────────────────┤",
        f"│ Company: {result.company_name[:35]:35s} │",
        f"│ Sector: {result.sector[:35]:35s} │",
        f"├───────────────────────────────────────────┤",
        f"│ SCORES (0-100)".ljust(43) + "│",
        f"│   Technical:        {result.technical_score:5.1f} {'':10s} │",
        f"│   Fundamental:      {result.fundamental_score:5.1f} {'':10s} │",
        f"│   ─────────────────────────────────────    │",
        f"│   COMBINED:         {result.combined_score:5.1f} {'':10s} │",
        f"├───────────────────────────────────────────┤",
        f"│ INVESTMENT STYLES".ljust(43) + "│",
        f"│   Value:   {result.value_score:5.1f}  │  Growth: {result.growth_score:5.1f}    │",
        f"│   Quality: {result.quality_score:5.1f}  │  Momentum: {result.momentum_score:3.1f}  │",
        f"├───────────────────────────────────────────┤",
        f"│ {emoji_map.get(result.combined_signal, '⚪')} Signal: {result.combined_signal:22s} │",
        f"│ {emoji_map.get(result.confidence, '⚪')} Confidence: {result.confidence:21s} │",
        f"│ 💪 Conviction: {result.conviction * 100:>5.0f}%{'':18s} │",
        f"└───────────────────────────────────────────┘",
    ]
    
    return "\n".join(lines)


# Singleton instance
combined_analyzer = CombinedAnalyzer()
