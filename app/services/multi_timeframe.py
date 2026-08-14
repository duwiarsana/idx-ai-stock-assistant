"""Multi-Timeframe Analysis Module.

Analyzes stocks across multiple timeframes to identify confluence and
higher-probability trading setups.

Timeframes:
- Short-term: 15 minutes (intraday)
- Medium-term: 1 hour (swing)
- Long-term: Daily (position)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional

import pandas as pd

from app.services.enhanced_technicals import (
    EnhancedTechnicalEngine,
    TechnicalAnalysisResult,
    TrendDirection,
)

logger = logging.getLogger(__name__)


# ── Enums ──────────────────────────────────────────────────────────────────

class Timeframe(Enum):
    SHORT = "15m"
    MEDIUM = "1h"
    LONG = "1D"


@dataclass
class TimeframeAnalysis:
    """Analysis result for a single timeframe."""
    timeframe: str
    result: TechnicalAnalysisResult
    weight: float


@dataclass
class MultiTimeframeResult:
    """Combined multi-timeframe analysis result."""
    ticker: str
    
    # Individual timeframe results
    short_term: TimeframeAnalysis
    medium_term: TimeframeAnalysis
    long_term: TimeframeAnalysis
    
    # Confluence
    confluence_score: float  # 0-100, how aligned are timeframes
    alignment_type: str  # FULL_ALIGNMENT, PARTIAL, CONFLICT
    
    # Final signal
    final_signal: str  # BUY, SELL, HOLD
    final_strength: str  # STRONG, MODERATE, WEAK
    confidence: str  # HIGH, MEDIUM, LOW
    
    # Summary
    summary: str
    
    def to_dict(self) -> dict:
        return asdict(self)


# ── Configuration ──────────────────────────────────────────────────────────

TIMEFRAME_WEIGHTS = {
    Timeframe.SHORT: 0.20,   # 15m - least weight for position trading
    Timeframe.MEDIUM: 0.30,  # 1h - medium weight
    Timeframe.LONG: 0.50,    # 1D - most weight
}

TIMEFRAME_CONFIG = {
    Timeframe.SHORT: {
        'period': '15m',
        'lookback': 100,
        'name': 'Short-term',
    },
    Timeframe.MEDIUM: {
        'period': '1h',
        'lookback': 100,
        'name': 'Medium-term',
    },
    Timeframe.LONG: {
        'period': '1D',
        'lookback': 200,
        'name': 'Long-term',
    },
}


# ── Multi-Timeframe Analyzer ──────────────────────────────────────────────

class MultiTimeframeAnalyzer:
    """Analyze stocks across multiple timeframes."""
    
    def __init__(self):
        self.engine = EnhancedTechnicalEngine()
    
    def analyze(
        self,
        ticker: str,
        data: dict[Timeframe, pd.DataFrame]
    ) -> MultiTimeframeResult:
        """Analyze stock across multiple timeframes.
        
        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        data : dict[Timeframe, pd.DataFrame]
            Dictionary mapping timeframes to OHLCV DataFrames
        
        Returns
        -------
        MultiTimeframeResult
            Combined analysis with confluence scoring
        """
        # Analyze each timeframe
        timeframe_results = {}
        for tf in Timeframe:
            if tf in data and not data[tf].empty:
                result = self.engine.analyze(data[tf], ticker)
                timeframe_results[tf] = TimeframeAnalysis(
                    timeframe=tf.value,
                    result=result,
                    weight=TIMEFRAME_WEIGHTS[tf],
                )
        
        # Calculate confluence
        confluence_score, alignment_type = self._calculate_confluence(timeframe_results)
        
        # Generate final signal
        final_signal, final_strength, confidence = self._generate_final_signal(
            timeframe_results, confluence_score, alignment_type
        )
        
        # Build summary
        summary = self._build_summary(timeframe_results, final_signal, confluence_score)
        
        return MultiTimeframeResult(
            ticker=ticker,
            short_term=timeframe_results.get(Timeframe.SHORT),
            medium_term=timeframe_results.get(Timeframe.MEDIUM),
            long_term=timeframe_results.get(Timeframe.LONG),
            confluence_score=round(confluence_score, 2),
            alignment_type=alignment_type,
            final_signal=final_signal,
            final_strength=final_strength,
            confidence=confidence,
            summary=summary,
        )
    
    def _calculate_confluence(
        self,
        results: dict[Timeframe, TimeframeAnalysis]
    ) -> tuple[float, str]:
        """Calculate how aligned the timeframes are.
        
        Returns
        -------
        tuple[float, str]
            confluence_score (0-100), alignment_type
        """
        if len(results) < 2:
            return 50.0, "INSUFFICIENT_DATA"
        
        # Get signals from each timeframe
        signals = []
        scores = []
        for tf, analysis in results.items():
            signal = analysis.result.signal
            score = analysis.result.composite_score
            signals.append(signal)
            scores.append(score)
        
        # Check signal alignment
        buy_count = sum(1 for s in signals if s == "BUY")
        sell_count = sum(1 for s in signals if s == "SELL")
        hold_count = sum(1 for s in signals if s == "HOLD")
        total = len(signals)
        
        # Calculate confluence score
        if buy_count == total or sell_count == total:
            # All timeframes agree
            confluence_score = 100.0
            alignment_type = "FULL_ALIGNMENT"
        elif (buy_count >= total - 1 and hold_count <= 1) or \
             (sell_count >= total - 1 and hold_count <= 1):
            # Strong agreement with one neutral
            confluence_score = 80.0
            alignment_type = "STRONG_ALIGNMENT"
        elif buy_count > 0 and sell_count > 0:
            # Conflict between timeframes
            confluence_score = 30.0
            alignment_type = "CONFLICT"
        elif hold_count == total:
            # All neutral
            confluence_score = 50.0
            alignment_type = "NEUTRAL"
        else:
            # Partial alignment
            confluence_score = 60.0
            alignment_type = "PARTIAL"
        
        # Adjust based on score similarity
        if len(scores) >= 2:
            score_std = pd.Series(scores).std()
            if score_std < 10:
                confluence_score = min(100, confluence_score + 10)
            elif score_std > 30:
                confluence_score = max(0, confluence_score - 10)
        
        return confluence_score, alignment_type
    
    def _generate_final_signal(
        self,
        results: dict[Timeframe, TimeframeAnalysis],
        confluence_score: float,
        alignment_type: str
    ) -> tuple[str, str, str]:
        """Generate final signal based on multi-timeframe analysis."""
        if not results:
            return "HOLD", "WEAK", "LOW"
        
        # Weighted score calculation
        weighted_score = 0.0
        total_weight = 0.0
        
        for tf, analysis in results.items():
            weight = analysis.weight
            score = analysis.result.composite_score
            weighted_score += score * weight
            total_weight += weight
        
        if total_weight > 0:
            weighted_score /= total_weight
        else:
            weighted_score = 50.0
        
        # Determine signal
        if weighted_score >= 70:
            signal = "BUY"
        elif weighted_score >= 55:
            signal = "BUY"
        elif weighted_score <= 30:
            signal = "SELL"
        elif weighted_score <= 45:
            signal = "SELL"
        else:
            signal = "HOLD"
        
        # Determine strength based on confluence
        if confluence_score >= 90:
            strength = "STRONG"
            confidence = "HIGH"
        elif confluence_score >= 70:
            strength = "MODERATE"
            confidence = "MEDIUM"
        elif confluence_score >= 50:
            strength = "WEAK"
            confidence = "MEDIUM"
        else:
            strength = "WEAK"
            confidence = "LOW"
        
        # Override for conflicts
        if alignment_type == "CONFLICT":
            strength = "WEAK"
            confidence = "LOW"
            signal = "HOLD"  # Don't trade in conflict
        
        # Override for full alignment
        if alignment_type == "FULL_ALIGNMENT":
            if signal == "BUY":
                strength = "STRONG"
                confidence = "HIGH"
            elif signal == "SELL":
                strength = "STRONG"
                confidence = "HIGH"
        
        return signal, strength, confidence
    
    def _build_summary(
        self,
        results: dict[Timeframe, TimeframeAnalysis],
        final_signal: str,
        confluence_score: float
    ) -> str:
        """Build human-readable summary."""
        lines = []
        
        for tf in [Timeframe.LONG, Timeframe.MEDIUM, Timeframe.SHORT]:
            if tf in results:
                analysis = results[tf]
                result = analysis.result
                emoji = {"BUY": "📈", "SELL": "📉", "HOLD": "⏸"}.get(result.signal, "❓")
                lines.append(
                    f"{TIMEFRAME_CONFIG[tf]['name']:12s} ({tf.value:3s}): "
                    f"{emoji} {result.signal} (score: {result.composite_score:.0f})"
                )
        
        # Add confluence info
        if confluence_score >= 80:
            lines.append(f"✓ Timeframes aligned ({confluence_score:.0f}% confluence)")
        elif confluence_score >= 50:
            lines.append(f"⚠ Partial alignment ({confluence_score:.0f}% confluence)")
        else:
            lines.append(f"✗ Timeframe conflict ({confluence_score:.0f}% confluence)")
        
        return " | ".join(lines)


# ── Resampling Utilities ──────────────────────────────────────────────────

class TimeframeResampler:
    """Resample minute data to different timeframes."""
    
    @staticmethod
    def resample_ohlcv(
        df: pd.DataFrame,
        timeframe: str,
        column_mapping: Optional[dict] = None
    ) -> pd.DataFrame:
        """Resample OHLCV data to different timeframe.
        
        Parameters
        ----------
        df : pd.DataFrame
            Minute-level OHLCV data with datetime index
        timeframe : str
            Target timeframe (e.g., '15T', '1H', '1D')
        column_mapping : dict, optional
            Mapping of standard names to column names in df
        
        Returns
        -------
        pd.DataFrame
            Resampled OHLCV data
        """
        if column_mapping is None:
            column_mapping = {
                'open': 'open',
                'high': 'high',
                'low': 'low',
                'close': 'close',
                'volume': 'volume',
            }
        
        # Ensure datetime index
        if not isinstance(df.index, pd.DatetimeIndex):
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df = df.set_index('date')
            else:
                raise ValueError("DataFrame must have datetime index or 'date' column")
        
        # Resample
        ohlcv_dict = {
            column_mapping['open']: 'first',
            column_mapping['high']: 'max',
            column_mapping['low']: 'min',
            column_mapping['close']: 'last',
            column_mapping['volume']: 'sum',
        }
        
        resampled = df.resample(timeframe).agg(ohlcv_dict)
        
        # Rename columns to standard names
        reverse_mapping = {v: k for k, v in column_mapping.items()}
        resampled = resampled.rename(columns=reverse_mapping)
        
        # Drop rows with all NaN
        resampled = resampled.dropna(how='all')
        
        return resampled
    
    @staticmethod
    def create_multi_timeframe_data(
        minute_df: pd.DataFrame,
        column_mapping: Optional[dict] = None
    ) -> dict[Timeframe, pd.DataFrame]:
        """Create multi-timeframe data from minute data.
        
        Parameters
        ----------
        minute_df : pd.DataFrame
            Minute-level OHLCV data
        column_mapping : dict, optional
            Column name mapping
        
        Returns
        -------
        dict[Timeframe, pd.DataFrame]
            Dictionary mapping timeframes to resampled DataFrames
        """
        return {
            Timeframe.SHORT: TimeframeResampler.resample_ohlcv(
                minute_df, '15T', column_mapping
            ),
            Timeframe.MEDIUM: TimeframeResampler.resample_ohlcv(
                minute_df, '1H', column_mapping
            ),
            Timeframe.LONG: TimeframeResampler.resample_ohlcv(
                minute_df, '1D', column_mapping
            ),
        }


# ── Formatting Utilities ──────────────────────────────────────────────────

def format_multi_timeframe_summary(result: MultiTimeframeResult) -> str:
    """Format multi-timeframe result for display."""
    emoji_map = {
        'BUY': '📈',
        'SELL': '📉',
        'HOLD': '⏸',
        'HIGH': '🟢',
        'MEDIUM': '🟡',
        'LOW': '🔴',
    }
    
    lines = [
        f"┌───────────────────────────────────────────┐",
        f"│ 📊 {result.ticker} - Multi-Timeframe Analysis",
        f"├───────────────────────────────────────────┤",
    ]
    
    # Timeframe breakdown
    for tf_name, tf_result in [
        ('Long-term (1D)', result.long_term),
        ('Medium-term (1h)', result.medium_term),
        ('Short-term (15m)', result.short_term),
    ]:
        if tf_result:
            signal_emoji = emoji_map.get(tf_result.result.signal, '❓')
            lines.append(
                f"│ {tf_name:18s}: {signal_emoji} {tf_result.result.signal:4s} "
                f"(score: {tf_result.result.composite_score:5.1f})"
            )
    
    lines.extend([
        f"├───────────────────────────────────────────┤",
        f"│ 🎯 Confluence: {result.confluence_score:5.1f}% ({result.alignment_type})",
        f"│",
        f"│ {emoji_map.get(result.final_signal, '❓')} Final Signal: {result.final_signal} ({result.final_strength})",
        f"│ 🎲 Confidence: {emoji_map.get(result.confidence, '❓')} {result.confidence}",
        f"└───────────────────────────────────────────┘",
    ])
    
    return "\n".join(lines)


# Singleton instance
multi_timeframe_analyzer = MultiTimeframeAnalyzer()
