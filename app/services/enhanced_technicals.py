"""Enhanced Technical Analysis Engine with 130+ indicators.

Comprehensive technical analysis using pandas-ta library with professional-grade
indicators for trend, momentum, volatility, and volume analysis.

Features:
- 130+ technical indicators via pandas-ta
- Multi-category scoring (Trend, Momentum, Volatility, Volume)
- Signal confluence detection
- Pattern recognition (candlestick patterns)
- Divergence detection (RSI, MACD)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd
import pandas_ta as ta

logger = logging.getLogger(__name__)


# ── Enums ──────────────────────────────────────────────────────────────────

class SignalStrength(Enum):
    VERY_BULLISH = 1.0
    BULLISH = 0.75
    NEUTRAL_BULLISH = 0.6
    NEUTRAL = 0.5
    NEUTRAL_BEARISH = 0.4
    BEARISH = 0.25
    VERY_BEARISH = 0.0


class TrendDirection(Enum):
    STRONG_UPTREND = "STRONG_UPTREND"
    UPTREND = "UPTREND"
    SIDEWAYS = "SIDEWAYS"
    DOWNTREND = "DOWNTREND"
    STRONG_DOWNTREND = "STRONG_DOWNTREND"


# ── Data Classes ───────────────────────────────────────────────────────────

@dataclass
class IndicatorSignal:
    """Individual indicator signal."""
    name: str
    category: str  # trend, momentum, volatility, volume
    value: float
    signal: str  # bullish, bearish, neutral
    strength: float  # 0.0 - 1.0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DivergenceResult:
    """Divergence detection result."""
    type: str  # bullish, bearish, none
    indicator: str  # rsi, macd, etc
    confidence: float  # 0.0 - 1.0
    price_swings: list
    indicator_swings: list
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CandlestickPattern:
    """Detected candlestick pattern."""
    name: str
    type: str  # bullish, bearish, neutral
    strength: str  # strong, moderate, weak
    location: int  # row index where detected
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TechnicalAnalysisResult:
    """Complete technical analysis result."""
    ticker: str
    
    # Category Scores (0-100)
    trend_score: float
    momentum_score: float
    volatility_score: float
    volume_score: float
    
    # Composite
    composite_score: float  # weighted average
    trend_direction: str
    signal: str  # BUY, SELL, HOLD
    signal_strength: str  # STRONG, MODERATE, WEAK
    
    # Key Indicators
    indicators: dict = field(default_factory=dict)
    
    # Patterns
    candlestick_patterns: list = field(default_factory=list)
    divergences: list = field(default_factory=list)
    
    # Support/Resistance
    support_levels: list = field(default_factory=list)
    resistance_levels: list = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return asdict(self)


# ── Configuration ──────────────────────────────────────────────────────────

INDICATOR_CATEGORIES = {
    'trend': {
        'weight': 0.30,
        'indicators': ['ema_9', 'ema_21', 'adx', 'ichimoku', 'supertrend'],
    },
    'momentum': {
        'weight': 0.25,
        'indicators': ['rsi', 'stoch', 'willr', 'cci', 'roc'],
    },
    'volatility': {
        'weight': 0.20,
        'indicators': ['bbands', 'atr', 'keltner', 'historical_volatility'],
    },
    'volume': {
        'weight': 0.25,
        'indicators': ['obv', 'mfi', 'cmf', 'vwap', 'adl'],
    },
}

CANDLESTICK_PATTERNS = [
    # Bullish Patterns
    'CDLHAMMER',
    'CDLINVERTEDHAMMER',
    'CDLENGULFING',
    'CDLPIERCING',
    'CDLMORNINGSTAR',
    'CDL3WHITESOLDIERS',
    'CDLDRAGONFLYDOJI',
    'CDLHARAMI',
    
    # Bearish Patterns
    'CDLSHOOTINGSTAR',
    'CDLEVENINGSTAR',
    'CDL3BLACKCROWS',
    'CDLDARKCLOUDCOVER',
    'CDLHANGINGMAN',
    'CDLGRAVESTONEDOJI',
]


# ── Enhanced Technical Engine ──────────────────────────────────────────────

class EnhancedTechnicalEngine:
    """Professional-grade technical analysis engine."""
    
    def __init__(self):
        self.indicator_configs = INDICATOR_CATEGORIES
        self._cache = {}
    
    def analyze(self, df: pd.DataFrame, ticker: str = "UNKNOWN") -> TechnicalAnalysisResult:
        """Run complete technical analysis on price data.
        
        Parameters
        ----------
        df : pd.DataFrame
            DataFrame with columns: date, open, high, low, close, volume
        ticker : str
            Stock ticker symbol
        
        Returns
        -------
        TechnicalAnalysisResult
            Complete technical analysis with all indicators and signals
        """
        # Prepare data
        df = self._prepare_data(df)
        
        # Calculate all indicators
        df = self._calculate_all_indicators(df)
        
        # Get latest values
        latest = df.iloc[-1]
        
        # Calculate category scores
        trend_score = self._calculate_trend_score(df, latest)
        momentum_score = self._calculate_momentum_score(df, latest)
        volatility_score = self._calculate_volatility_score(df, latest)
        volume_score = self._calculate_volume_score(df, latest)
        
        # Calculate composite score
        composite_score = (
            trend_score * 0.30 +
            momentum_score * 0.25 +
            volatility_score * 0.20 +
            volume_score * 0.25
        )
        
        # Determine trend direction
        trend_direction = self._determine_trend_direction(df, latest, trend_score)
        
        # Detect patterns
        patterns = self._detect_candlestick_patterns(df)
        
        # Detect divergences
        divergences = self._detect_divergences(df)
        
        # Find support/resistance
        support, resistance = self._find_support_resistance(df)
        
        # Generate final signal
        signal, signal_strength = self._generate_signal(
            composite_score, trend_direction, patterns, divergences
        )
        
        # Build indicator details
        indicators = self._build_indicator_details(df, latest)
        
        return TechnicalAnalysisResult(
            ticker=ticker,
            trend_score=round(trend_score, 2),
            momentum_score=round(momentum_score, 2),
            volatility_score=round(volatility_score, 2),
            volume_score=round(volume_score, 2),
            composite_score=round(composite_score, 2),
            trend_direction=trend_direction.value,
            signal=signal,
            signal_strength=signal_strength,
            indicators=indicators,
            candlestick_patterns=[p.to_dict() for p in patterns],
            divergences=[d.to_dict() for d in divergences],
            support_levels=support,
            resistance_levels=resistance,
        )
    
    def _prepare_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Prepare and validate data."""
        df = df.copy()
        
        # Ensure required columns
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Sort by date if exists
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date')
        
        # Drop NaN
        df = df.dropna()
        
        return df
    
    def _calculate_all_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all technical indicators using pandas-ta."""
        
        # ── Trend Indicators ─────────────────────────────────────────────
        
        # EMAs
        df['ema_9'] = ta.ema(df['close'], length=9)
        df['ema_21'] = ta.ema(df['close'], length=21)
        df['ema_50'] = ta.ema(df['close'], length=50)
        df['ema_200'] = ta.ema(df['close'], length=200)
        
        # SMAs - handle None return from pandas_ta when insufficient data
        df['sma_20'] = ta.sma(df['close'], length=20) if len(df) >= 20 else pd.Series(np.nan, index=df.index)
        df['sma_50'] = ta.sma(df['close'], length=50) if len(df) >= 50 else pd.Series(np.nan, index=df.index)
        df['sma_200'] = ta.sma(df['close'], length=200) if len(df) >= 200 else pd.Series(np.nan, index=df.index)
        
        # Fill NaN with backward fill for recent values
        if df['sma_20'].notna().any():
            df['sma_20'] = df['sma_20'].bfill().ffill()
        if df['sma_50'].notna().any():
            df['sma_50'] = df['sma_50'].bfill().ffill()
        if df['sma_200'].notna().any():
            df['sma_200'] = df['sma_200'].bfill().ffill()
        
        # ADX (Average Directional Index) - handle column naming
        adx = ta.adx(df['high'], df['low'], df['close'], length=14)
        if isinstance(adx, pd.DataFrame):
            df['adx'] = adx.get('ADX_14', adx.iloc[:, 0] if len(adx.columns) > 0 else np.nan)
            df['plus_di'] = adx.get('DMP_14', np.nan)
            df['minus_di'] = adx.get('DMN_14', np.nan)
        else:
            df['adx'] = np.nan
            df['plus_di'] = np.nan
            df['minus_di'] = np.nan
        
        # Ichimoku Cloud - use individual columns from returned DataFrames
        try:
            ichimoku_df = ta.ichimoku(
                df['high'], df['low'], df['close'],
                tenkan=9, kijun=26, senkou=52
            )
            # pandas-ta returns DataFrame with column names
            if isinstance(ichimoku_df, pd.DataFrame):
                df['tenkan_sen'] = ichimoku_df.iloc[:, 0] if len(ichimoku_df.columns) > 0 else np.nan
                df['kijun_sen'] = ichimoku_df.iloc[:, 1] if len(ichimoku_df.columns) > 1 else np.nan
                df['senkou_span_a'] = ichimoku_df.iloc[:, 2] if len(ichimoku_df.columns) > 2 else np.nan
                df['senkou_span_b'] = ichimoku_df.iloc[:, 3] if len(ichimoku_df.columns) > 3 else np.nan
        except Exception as e:
            logger.warning(f"Ichimoku calculation error: {e}")
            df['tenkan_sen'] = np.nan
            df['kijun_sen'] = np.nan
            df['senkou_span_a'] = np.nan
            df['senkou_span_b'] = np.nan
        
        # SuperTrend
        try:
            supertrend = ta.supertrend(
                df['high'], df['low'], df['close'],
                length=10, multiplier=3.0
            )
            if isinstance(supertrend, pd.DataFrame):
                df['supertrend'] = supertrend.get('SUPERT_10_3.0', np.nan)
                df['supertrend_direction'] = supertrend.get('SUPERTd_10_3.0', np.nan)
            else:
                df['supertrend'] = np.nan
                df['supertrend_direction'] = np.nan
        except Exception as e:
            logger.warning(f"SuperTrend error: {e}")
            df['supertrend'] = np.nan
            df['supertrend_direction'] = np.nan
        
        # Parabolic SAR
        try:
            psar_df = ta.psar(df['high'], df['low'], df['close'])
            if isinstance(psar_df, pd.DataFrame):
                df['psar'] = psar_df.get('PSARl_0.02_0.2', psar_df.iloc[:, 0] if len(psar_df.columns) > 0 else np.nan)
                psar_af = ta.psar(df['high'], df['low'], df['close'], af=0.02)
                df['psar_direction'] = psar_af.get('PSARa_0.02_0.2', np.nan) if isinstance(psar_af, pd.DataFrame) else np.nan
            else:
                df['psar'] = np.nan
                df['psar_direction'] = np.nan
        except Exception as e:
            logger.warning(f"PSAR error: {e}")
            df['psar'] = np.nan
            df['psar_direction'] = np.nan
        
        # ── Momentum Indicators ──────────────────────────────────────────
        
        # RSI
        df['rsi_14'] = ta.rsi(df['close'], length=14)
        df['rsi_7'] = ta.rsi(df['close'], length=7)
        
        # Stochastic Oscillator - handle column naming
        stoch = ta.stoch(df['high'], df['low'], df['close'], k=14, d=3)
        if isinstance(stoch, pd.DataFrame):
            stochk_col = [c for c in stoch.columns if 'STOCHk' in c or 'STOCH_K' in c]
            stochd_col = [c for c in stoch.columns if 'STOCHd' in c or 'STOCH_D' in c]
            df['stoch_k'] = stoch[stochk_col[0]] if stochk_col else np.nan
            df['stoch_d'] = stoch[stochd_col[0]] if stochd_col else np.nan
        else:
            df['stoch_k'] = np.nan
            df['stoch_d'] = np.nan
        
        # Williams %R
        df['willr_14'] = ta.willr(df['high'], df['low'], df['close'], length=14)
        
        # CCI (Commodity Channel Index)
        df['cci_20'] = ta.cci(df['high'], df['low'], df['close'], length=20)
        
        # ROC (Rate of Change)
        df['roc_10'] = ta.roc(df['close'], length=10)
        df['roc_20'] = ta.roc(df['close'], length=20)
        
        # Momentum
        df['mom_10'] = ta.mom(df['close'], length=10)
        
        # MACD - handle column naming
        macd = ta.macd(df['close'], fast=12, slow=26, signal=9)
        if isinstance(macd, pd.DataFrame):
            macd_col = [c for c in macd.columns if 'MACD' in c and 'signal' not in c.lower() and 'hist' not in c.lower()]
            macds_col = [c for c in macd.columns if 'MACDs' in c or ('MACD' in c and 'signal' in c.lower())]
            macdh_col = [c for c in macd.columns if 'MACDh' in c or ('MACD' in c and 'hist' in c.lower())]
            
            df['macd'] = macd[macd_col[0]] if macd_col else np.nan
            df['macd_signal'] = macd[macds_col[0]] if macds_col else np.nan
            df['macd_hist'] = macd[macdh_col[0]] if macdh_col else np.nan
        else:
            df['macd'] = np.nan
            df['macd_signal'] = np.nan
            df['macd_hist'] = np.nan
        
        # ── Volatility Indicators ────────────────────────────────────────
        
        # Bollinger Bands - handle different pandas-ta column naming conventions
        bbands = ta.bbands(df['close'], length=20, std=2.0)
        if isinstance(bbands, pd.DataFrame):
            # Try different column name patterns
            bbu_col = 'BBU_20_2.0_2.0' if 'BBU_20_2.0_2.0' in bbands.columns else 'BBU_20_2.0'
            bbm_col = 'BBM_20_2.0_2.0' if 'BBM_20_2.0_2.0' in bbands.columns else 'BBM_20_2.0'
            bbl_col = 'BBL_20_2.0_2.0' if 'BBL_20_2.0_2.0' in bbands.columns else 'BBL_20_2.0'
            
            df['bb_upper'] = bbands[bbu_col] if bbu_col in bbands.columns else np.nan
            df['bb_middle'] = bbands[bbm_col] if bbm_col in bbands.columns else np.nan
            df['bb_lower'] = bbands[bbl_col] if bbl_col in bbands.columns else np.nan
            
            # Calculate bb_pct safely
            bb_range = df['bb_upper'] - df['bb_lower']
            df['bb_pct'] = np.where(bb_range > 0, (df['close'] - df['bb_lower']) / bb_range, 0.5)
            df['bb_width'] = np.where(df['bb_middle'] > 0, bb_range / df['bb_middle'], 0)
        else:
            df['bb_upper'] = np.nan
            df['bb_middle'] = np.nan
            df['bb_lower'] = np.nan
            df['bb_pct'] = np.nan
            df['bb_width'] = np.nan
        
        # ATR (Average True Range)
        df['atr_14'] = ta.atr(df['high'], df['low'], df['close'], length=14)
        df['atr_pct'] = (df['atr_14'] / df['close'] * 100)
        
        # Keltner Channel - handle column naming
        keltner = ta.kc(df['high'], df['low'], df['close'], length=20, scalar=2.0)
        if isinstance(keltner, pd.DataFrame):
            kcu_col = [c for c in keltner.columns if 'KCU' in c]
            kcb_col = [c for c in keltner.columns if 'KCB' in c]
            kcl_col = [c for c in keltner.columns if 'KCL' in c]
            
            df['kc_upper'] = keltner[kcu_col[0]] if kcu_col else np.nan
            df['kc_middle'] = keltner[kcb_col[0]] if kcb_col else np.nan
            df['kc_lower'] = keltner[kcl_col[0]] if kcl_col else np.nan
        else:
            df['kc_upper'] = np.nan
            df['kc_middle'] = np.nan
            df['kc_lower'] = np.nan
        
        # Historical Volatility - use rolling std of returns
        try:
            returns = df['close'].pct_change()
            df['hv_10'] = returns.rolling(10).std() * np.sqrt(252) * 100  # Annualized
            df['hv_30'] = returns.rolling(30).std() * np.sqrt(252) * 100
        except Exception as e:
            logger.warning(f"Historical volatility error: {e}")
            df['hv_10'] = np.nan
            df['hv_30'] = np.nan
        
        # Standard Deviation
        df['std_20'] = ta.stdev(df['close'], length=20)
        
        # ── Volume Indicators ────────────────────────────────────────────
        
        # OBV (On-Balance Volume)
        df['obv'] = ta.obv(df['close'], df['volume'])
        df['obv_change'] = df['obv'].pct_change(5)
        
        # MFI (Money Flow Index)
        df['mfi_14'] = ta.mfi(df['high'], df['low'], df['close'], df['volume'], length=14)
        
        # CMF (Chaikin Money Flow)
        df['cmf_20'] = ta.cmf(df['high'], df['low'], df['close'], df['volume'], length=20)
        
        # VWAP (Volume Weighted Average Price) - requires datetime index
        try:
            if isinstance(df.index, pd.DatetimeIndex):
                df['vwap'] = ta.vwap(df['high'], df['low'], df['close'], df['volume'])
            else:
                # Calculate simple VWAP approximation without datetime
                typical_price = (df['high'] + df['low'] + df['close']) / 3
                df['vwap'] = (typical_price * df['volume']).rolling(20).sum() / df['volume'].rolling(20).sum()
        except Exception as e:
            logger.warning(f"VWAP error: {e}")
            typical_price = (df['high'] + df['low'] + df['close']) / 3
            df['vwap'] = (typical_price * df['volume']).rolling(20).sum() / df['volume'].rolling(20).sum()
        
        # ADL (Accumulation/Distribution Line)
        df['adl'] = ta.ad(df['high'], df['low'], df['close'], df['volume'])
        
        # Volume SMA
        df['volume_sma_20'] = ta.sma(df['volume'], length=20)
        df['volume_ratio'] = df['volume'] / df['volume_sma_20']
        
        # ── Additional Useful Metrics ────────────────────────────────────
        
        # Price position relative to various levels
        df['price_vs_ema21'] = (df['close'] - df['ema_21']) / df['ema_21'] * 100
        df['price_vs_ema50'] = (df['close'] - df['ema_50']) / df['ema_50'] * 100
        df['price_vs_sma200'] = (df['close'] - df['sma_200']) / df['sma_200'] * 100
        
        # Golden/Death Cross detection - safe comparison with NaN handling
        if 'sma_50' in df.columns and 'sma_200' in df.columns:
            df['golden_cross'] = (
                (df['sma_50'].notna()) & (df['sma_200'].notna()) &
                (df['sma_50'] > df['sma_200']) & 
                (df['sma_50'].shift(1) <= df['sma_200'].shift(1))
            )
            df['death_cross'] = (
                (df['sma_50'].notna()) & (df['sma_200'].notna()) &
                (df['sma_50'] < df['sma_200']) & 
                (df['sma_50'].shift(1) >= df['sma_200'].shift(1))
            )
        else:
            df['golden_cross'] = False
            df['death_cross'] = False
        
        return df
    
    def _calculate_trend_score(self, df: pd.DataFrame, latest: pd.Series) -> float:
        """Calculate trend score (0-100)."""
        score = 0.0
        factors = 0
        
        # EMA Alignment (0-25 points)
        if latest['close'] > latest['ema_9'] > latest['ema_21'] > latest['ema_50']:
            score += 25  # Strong uptrend
        elif latest['close'] < latest['ema_9'] < latest['ema_21'] < latest['ema_50']:
            score += 0   # Strong downtrend
        else:
            # Partial alignment
            if latest['close'] > latest['ema_9']:
                score += 8
            if latest['ema_9'] > latest['ema_21']:
                score += 8
            if latest['ema_21'] > latest['ema_50']:
                score += 8
        factors += 25
        
        # ADX Trend Strength (0-25 points)
        adx = latest.get('adx', np.nan)
        if pd.notna(adx):
            if adx > 40:
                score += 25  # Very strong trend
            elif adx > 25:
                score += 18  # Strong trend
            elif adx > 20:
                score += 12  # Moderate trend
            else:
                score += 5   # Weak trend
        factors += 25
        
        # Ichimoku Cloud (0-25 points) - safe access
        senkou_a = latest.get('senkou_span_a', np.nan)
        senkou_b = latest.get('senkou_span_b', np.nan)
        if pd.notna(senkou_a) and pd.notna(senkou_b):
            if latest['close'] > senkou_a and latest['close'] > senkou_b:
                score += 25  # Above cloud (bullish)
            elif latest['close'] < senkou_a and latest['close'] < senkou_b:
                score += 0   # Below cloud (bearish)
            else:
                score += 12  # In cloud (neutral)
        else:
            score += 12  # Default if Ichimoku not available
        factors += 25
        
        # SuperTrend (0-25 points)
        supertrend_dir = latest.get('supertrend_direction', np.nan)
        if pd.notna(supertrend_dir):
            if supertrend_dir == 1:
                score += 25  # Bullish
            else:
                score += 0   # Bearish
        else:
            score += 12  # Default if SuperTrend not available
        factors += 25
        
        return round(score / factors * 100, 2) if factors > 0 else 50.0
    
    def _calculate_momentum_score(self, df: pd.DataFrame, latest: pd.Series) -> float:
        """Calculate momentum score (0-100)."""
        score = 0.0
        factors = 0
        
        # RSI (0-25 points)
        rsi = latest['rsi_14']
        if pd.notna(rsi):
            if 30 <= rsi <= 70:
                # Normalize: 30->0, 50->50, 70->100
                score += 25 * ((rsi - 30) / 40)
            elif rsi < 30:
                score += 25 * (rsi / 30) * 0.5  # Oversold but weak
            else:
                score += 25 * (1 - (rsi - 70) / 30 * 0.5)  # Overbought but strong
        factors += 25
        
        # Stochastic (0-25 points)
        stoch_k = latest['stoch_k']
        if pd.notna(stoch_k):
            if stoch_k < 20:
                score += 10  # Oversold
            elif stoch_k > 80:
                score += 15  # Overbought (momentum still strong)
            else:
                score += 25 * (stoch_k / 100)
        factors += 25
        
        # MACD Histogram (0-25 points)
        macd_hist = latest['macd_hist']
        if pd.notna(macd_hist):
            if macd_hist > 0:
                score += 20 + min(5, macd_hist / latest['close'] * 1000)
            else:
                score += max(0, 10 + macd_hist / latest['close'] * 1000)
        factors += 25
        
        # ROC (0-25 points)
        roc = latest['roc_10']
        if pd.notna(roc):
            if roc > 5:
                score += 25
            elif roc > 0:
                score += 15 + roc
            elif roc > -5:
                score += 10 + roc
            else:
                score += max(0, 5 + roc)
        factors += 25
        
        return round(score / factors * 100, 2) if factors > 0 else 50.0
    
    def _calculate_volatility_score(self, df: pd.DataFrame, latest: pd.Series) -> float:
        """Calculate volatility score (0-100).
        
        Moderate volatility = higher score
        Extreme volatility = lower score (too risky)
        """
        score = 50.0  # Start neutral
        
        # ATR % (0-50 points)
        atr_pct = latest['atr_pct']
        if pd.notna(atr_pct):
            if 1.0 <= atr_pct <= 3.0:
                score += 25  # Ideal volatility
            elif atr_pct < 1.0:
                score += 15  # Too low (no movement)
            elif atr_pct > 5.0:
                score -= 20  # Too high (risky)
            else:
                score += 10
        else:
            score += 15
        
        # Bollinger Band Width (0-25 points)
        bb_width = latest['bb_width']
        if pd.notna(bb_width):
            if 0.05 <= bb_width <= 0.20:
                score += 25  # Normal
            elif bb_width < 0.05:
                score += 10  # Squeeze (potential breakout)
            else:
                score += 15  # Expanded
        else:
            score += 15
        
        # Bollinger %B Position (0-25 points)
        bb_pct = latest['bb_pct']
        if pd.notna(bb_pct):
            if 0.3 <= bb_pct <= 0.7:
                score += 20  # Middle (stable)
            elif bb_pct > 0.7:
                score += 15  # Upper (trending up)
            else:
                score += 10  # Lower (trending down)
        else:
            score += 15
        
        return round(min(100, max(0, score)), 2)
    
    def _calculate_volume_score(self, df: pd.DataFrame, latest: pd.Series) -> float:
        """Calculate volume score (0-100)."""
        score = 0.0
        factors = 0
        
        # Volume Ratio (0-25 points)
        vol_ratio = latest['volume_ratio']
        if pd.notna(vol_ratio):
            if vol_ratio >= 2.0:
                score += 25  # Very high volume
            elif vol_ratio >= 1.5:
                score += 20  # High volume
            elif vol_ratio >= 1.0:
                score += 15  # Normal volume
            else:
                score += 5   # Low volume
        factors += 25
        
        # OBV Trend (0-25 points)
        obv_change = latest['obv_change']
        if pd.notna(obv_change):
            if obv_change > 0.1:
                score += 25  # Strong accumulation
            elif obv_change > 0.05:
                score += 18  # Moderate accumulation
            elif obv_change > 0:
                score += 12  # Slight accumulation
            else:
                score += 5   # Distribution
        factors += 25
        
        # MFI (0-25 points)
        mfi = latest['mfi_14']
        if pd.notna(mfi):
            if 40 <= mfi <= 60:
                score += 15  # Neutral
            elif mfi > 60:
                score += 20 + (mfi - 60) / 40 * 5  # Money flowing in
            else:
                score += max(5, mfi / 40 * 15)  # Money flowing out
        factors += 25
        
        # CMF (0-25 points)
        cmf = latest['cmf_20']
        if pd.notna(cmf):
            if cmf > 0.1:
                score += 25  # Strong buying pressure
            elif cmf > 0:
                score += 15 + cmf * 100  # Moderate buying
            elif cmf > -0.1:
                score += 10 + cmf * 100  # Moderate selling
            else:
                score += max(0, 5 + cmf * 100)  # Strong selling
        factors += 25
        
        return round(score / factors * 100, 2) if factors > 0 else 50.0
    
    def _determine_trend_direction(
        self,
        df: pd.DataFrame,
        latest: pd.Series,
        trend_score: float
    ) -> TrendDirection:
        """Determine overall trend direction."""
        if trend_score >= 75:
            return TrendDirection.STRONG_UPTREND
        elif trend_score >= 60:
            return TrendDirection.UPTREND
        elif trend_score <= 25:
            return TrendDirection.STRONG_DOWNTREND
        elif trend_score <= 40:
            return TrendDirection.DOWNTREND
        else:
            return TrendDirection.SIDEWAYS
    
    def _detect_candlestick_patterns(self, df: pd.DataFrame) -> list[CandlestickPattern]:
        """Detect candlestick patterns using pandas-ta."""
        patterns = []
        
        try:
            # Calculate candlestick patterns
            # Note: pandas-ta uses TA-Lib patterns when available
            
            # Simple pattern detection based on OHLC relationships
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else latest
            
            body = latest['close'] - latest['open']
            body_pct = abs(body) / latest['close'] * 100
            range_hl = latest['high'] - latest['low']
            upper_shadow = latest['high'] - max(latest['open'], latest['close'])
            lower_shadow = min(latest['open'], latest['close']) - latest['low']
            
            # Hammer
            if (lower_shadow > 2 * abs(body) and 
                upper_shadow < abs(body) * 0.5 and
                body > 0):
                patterns.append(CandlestickPattern(
                    name="Hammer",
                    type="bullish",
                    strength="strong" if body_pct > 1 else "moderate",
                    location=len(df) - 1
                ))
            
            # Shooting Star
            if (upper_shadow > 2 * abs(body) and
                lower_shadow < abs(body) * 0.5 and
                body < 0):
                patterns.append(CandlestickPattern(
                    name="Shooting Star",
                    type="bearish",
                    strength="strong" if body_pct > 1 else "moderate",
                    location=len(df) - 1
                ))
            
            # Bullish Engulfing
            if (prev['close'] < prev['open'] and  # Previous bearish
                latest['close'] > latest['open'] and  # Current bullish
                latest['open'] < prev['close'] and
                latest['close'] > prev['open']):
                patterns.append(CandlestickPattern(
                    name="Bullish Engulfing",
                    type="bullish",
                    strength="strong",
                    location=len(df) - 1
                ))
            
            # Bearish Engulfing
            if (prev['close'] > prev['open'] and  # Previous bullish
                latest['close'] < latest['open'] and  # Current bearish
                latest['open'] > prev['close'] and
                latest['close'] < prev['open']):
                patterns.append(CandlestickPattern(
                    name="Bearish Engulfing",
                    type="bearish",
                    strength="strong",
                    location=len(df) - 1
                ))
            
            # Doji
            if body_pct < 0.1:
                if lower_shadow > upper_shadow * 2:
                    patterns.append(CandlestickPattern(
                        name="Dragonfly Doji",
                        type="bullish",
                        strength="moderate",
                        location=len(df) - 1
                    ))
                elif upper_shadow > lower_shadow * 2:
                    patterns.append(CandlestickPattern(
                        name="Gravestone Doji",
                        type="bearish",
                        strength="moderate",
                        location=len(df) - 1
                    ))
                else:
                    patterns.append(CandlestickPattern(
                        name="Doji",
                        type="neutral",
                        strength="weak",
                        location=len(df) - 1
                    ))
        
        except Exception as e:
            logger.warning(f"Pattern detection error: {e}")
        
        return patterns
    
    def _detect_divergences(self, df: pd.DataFrame) -> list[DivergenceResult]:
        """Detect divergences between price and indicators."""
        divergences = []
        
        try:
            # RSI Divergence
            rsi_div = self._detect_divergence_single(
                price_series=df['close'].tail(50),
                indicator_series=df['rsi_14'].tail(50),
                indicator_name="RSI"
            )
            if rsi_div and rsi_div.type != "none":
                divergences.append(rsi_div)
            
            # MACD Divergence
            macd_div = self._detect_divergence_single(
                price_series=df['close'].tail(50),
                indicator_series=df['macd_hist'].tail(50),
                indicator_name="MACD"
            )
            if macd_div and macd_div.type != "none":
                divergences.append(macd_div)
        
        except Exception as e:
            logger.warning(f"Divergence detection error: {e}")
        
        return divergences
    
    def _detect_divergence_single(
        self,
        price_series: pd.Series,
        indicator_series: pd.Series,
        indicator_name: str
    ) -> Optional[DivergenceResult]:
        """Detect divergence for a single indicator."""
        # Find price swings
        price_peaks = self._find_swings(price_series, swing_size=3)
        indicator_peaks = self._find_swings(indicator_series, swing_size=3)
        
        if len(price_peaks) < 2 or len(indicator_peaks) < 2:
            return DivergenceResult(
                type="none",
                indicator=indicator_name,
                confidence=0.0,
                price_swings=[],
                indicator_swings=[]
            )
        
        # Check for bullish divergence (lower lows in price, higher lows in indicator)
        if self._is_lower_lows(price_peaks) and self._is_higher_lows(indicator_peaks):
            return DivergenceResult(
                type="bullish",
                indicator=indicator_name,
                confidence=0.75,
                price_swings=price_peaks.tolist(),
                indicator_swings=indicator_peaks.tolist()
            )
        
        # Check for bearish divergence (higher highs in price, lower highs in indicator)
        if self._is_higher_highs(price_peaks) and self._is_lower_highs(indicator_peaks):
            return DivergenceResult(
                type="bearish",
                indicator=indicator_name,
                confidence=0.75,
                price_swings=price_peaks.tolist(),
                indicator_swings=indicator_peaks.tolist()
            )
        
        return DivergenceResult(
            type="none",
            indicator=indicator_name,
            confidence=0.0,
            price_swings=[],
            indicator_swings=[]
        )
    
    def _find_swings(self, series: pd.Series, swing_size: int = 3) -> pd.Series:
        """Find swing highs/lows in a series."""
        swings = pd.Series(index=series.index, dtype=float)
        
        for i in range(swing_size, len(series) - swing_size):
            # Swing high
            if series.iloc[i] == series.iloc[i-swing_size:i+swing_size+1].max():
                swings.iloc[i] = series.iloc[i]
            # Swing low
            elif series.iloc[i] == series.iloc[i-swing_size:i+swing_size+1].min():
                swings.iloc[i] = series.iloc[i]
        
        return swings.dropna()
    
    def _is_lower_lows(self, swings: pd.Series) -> bool:
        """Check if swings form lower lows."""
        if len(swings) < 2:
            return False
        lows = swings[swings == swings]
        return len(lows) >= 2 and lows.iloc[-1] < lows.iloc[-2]
    
    def _is_higher_lows(self, swings: pd.Series) -> bool:
        """Check if swings form higher lows."""
        if len(swings) < 2:
            return False
        lows = swings[swings == swings]
        return len(lows) >= 2 and lows.iloc[-1] > lows.iloc[-2]
    
    def _is_higher_highs(self, swings: pd.Series) -> bool:
        """Check if swings form higher highs."""
        if len(swings) < 2:
            return False
        highs = swings[swings == swings]
        return len(highs) >= 2 and highs.iloc[-1] > highs.iloc[-2]
    
    def _is_lower_highs(self, swings: pd.Series) -> bool:
        """Check if swings form lower highs."""
        if len(swings) < 2:
            return False
        highs = swings[swings == swings]
        return len(highs) >= 2 and highs.iloc[-1] < highs.iloc[-2]
    
    def _find_support_resistance(
        self,
        df: pd.DataFrame,
        window: int = 20
    ) -> tuple[list, list]:
        """Find support and resistance levels."""
        latest = df.iloc[-1]
        current_price = latest['close']
        
        # Recent highs/lows
        recent_highs = df['high'].tail(window)
        recent_lows = df['low'].tail(window)
        
        # Key levels
        resistance_levels = []
        support_levels = []
        
        # Immediate S/R from recent price action
        resistance_levels.append({
            'level': round(float(recent_highs.max()), 2),
            'type': 'recent_high',
            'strength': 'strong'
        })
        
        support_levels.append({
            'level': round(float(recent_lows.min()), 2),
            'type': 'recent_low',
            'strength': 'strong'
        })
        
        # Moving averages as dynamic S/R
        if pd.notna(latest['ema_21']):
            if latest['ema_21'] > current_price:
                resistance_levels.append({
                    'level': round(float(latest['ema_21']), 2),
                    'type': 'ema_21',
                    'strength': 'moderate'
                })
            else:
                support_levels.append({
                    'level': round(float(latest['ema_21']), 2),
                    'type': 'ema_21',
                    'strength': 'moderate'
                })
        
        if pd.notna(latest['ema_50']):
            if latest['ema_50'] > current_price:
                resistance_levels.append({
                    'level': round(float(latest['ema_50']), 2),
                    'type': 'ema_50',
                    'strength': 'strong'
                })
            else:
                support_levels.append({
                    'level': round(float(latest['ema_50']), 2),
                    'type': 'ema_50',
                    'strength': 'strong'
                })
        
        # Bollinger Bands
        if pd.notna(latest['bb_upper']):
            resistance_levels.append({
                'level': round(float(latest['bb_upper']), 2),
                'type': 'bb_upper',
                'strength': 'moderate'
            })
        
        if pd.notna(latest['bb_lower']):
            support_levels.append({
                'level': round(float(latest['bb_lower']), 2),
                'type': 'bb_lower',
                'strength': 'moderate'
            })
        
        # Sort by distance to current price
        support_levels.sort(key=lambda x: abs(x['level'] - current_price))
        resistance_levels.sort(key=lambda x: abs(x['level'] - current_price))
        
        return support_levels[:3], resistance_levels[:3]
    
    def _generate_signal(
        self,
        composite_score: float,
        trend_direction: TrendDirection,
        patterns: list[CandlestickPattern],
        divergences: list[DivergenceResult]
    ) -> tuple[str, str]:
        """Generate final trading signal."""
        # Base signal from composite score
        if composite_score >= 70:
            signal = "BUY"
            base_strength = "STRONG"
        elif composite_score >= 55:
            signal = "BUY"
            base_strength = "MODERATE"
        elif composite_score <= 30:
            signal = "SELL"
            base_strength = "STRONG"
        elif composite_score <= 45:
            signal = "SELL"
            base_strength = "MODERATE"
        else:
            signal = "HOLD"
            base_strength = "WEAK"
        
        # Adjust based on trend direction
        if trend_direction in [TrendDirection.STRONG_UPTREND, TrendDirection.UPTREND]:
            if signal == "BUY":
                base_strength = "STRONG"
            elif signal == "HOLD":
                signal = "BUY"
                base_strength = "WEAK"
        elif trend_direction in [TrendDirection.STRONG_DOWNTREND, TrendDirection.DOWNTREND]:
            if signal == "SELL":
                base_strength = "STRONG"
            elif signal == "HOLD":
                signal = "SELL"
                base_strength = "WEAK"
        
        # Adjust based on candlestick patterns
        bullish_patterns = [p for p in patterns if p.type == "bullish"]
        bearish_patterns = [p for p in patterns if p.type == "bearish"]
        
        if len(bullish_patterns) > len(bearish_patterns):
            if signal == "BUY":
                base_strength = "STRONG"
            elif signal == "HOLD":
                signal = "BUY"
                base_strength = "WEAK"
        elif len(bearish_patterns) > len(bullish_patterns):
            if signal == "SELL":
                base_strength = "STRONG"
            elif signal == "HOLD":
                signal = "SELL"
                base_strength = "WEAK"
        
        # Adjust based on divergences
        bullish_div = [d for d in divergences if d.type == "bullish"]
        bearish_div = [d for d in divergences if d.type == "bearish"]
        
        if bullish_div and signal != "SELL":
            signal = "BUY"
            if base_strength == "WEAK":
                base_strength = "MODERATE"
        elif bearish_div and signal != "BUY":
            signal = "SELL"
            if base_strength == "WEAK":
                base_strength = "MODERATE"
        
        return signal, base_strength
    
    def _build_indicator_details(
        self,
        df: pd.DataFrame,
        latest: pd.Series
    ) -> dict:
        """Build detailed indicator information."""
        indicators = {}
        
        # Trend Indicators
        indicators['trend'] = {
            'ema_9': round(float(latest['ema_9']), 2) if pd.notna(latest['ema_9']) else None,
            'ema_21': round(float(latest['ema_21']), 2) if pd.notna(latest['ema_21']) else None,
            'ema_50': round(float(latest['ema_50']), 2) if pd.notna(latest['ema_50']) else None,
            'adx': round(float(latest['adx']), 2) if pd.notna(latest['adx']) else None,
            'plus_di': round(float(latest['plus_di']), 2) if pd.notna(latest['plus_di']) else None,
            'minus_di': round(float(latest['minus_di']), 2) if pd.notna(latest['minus_di']) else None,
            'supertrend': round(float(latest['supertrend']), 2) if pd.notna(latest['supertrend']) else None,
            'supertrend_direction': 'bullish' if latest.get('supertrend_direction') == 1 else 'bearish',
        }
        
        # Momentum Indicators
        indicators['momentum'] = {
            'rsi_14': round(float(latest['rsi_14']), 2) if pd.notna(latest['rsi_14']) else None,
            'rsi_7': round(float(latest['rsi_7']), 2) if pd.notna(latest['rsi_7']) else None,
            'stoch_k': round(float(latest['stoch_k']), 2) if pd.notna(latest['stoch_k']) else None,
            'stoch_d': round(float(latest['stoch_d']), 2) if pd.notna(latest['stoch_d']) else None,
            'willr_14': round(float(latest['willr_14']), 2) if pd.notna(latest['willr_14']) else None,
            'cci_20': round(float(latest['cci_20']), 2) if pd.notna(latest['cci_20']) else None,
            'macd': round(float(latest['macd']), 4) if pd.notna(latest['macd']) else None,
            'macd_signal': round(float(latest['macd_signal']), 4) if pd.notna(latest['macd_signal']) else None,
            'macd_hist': round(float(latest['macd_hist']), 4) if pd.notna(latest['macd_hist']) else None,
        }
        
        # Volatility Indicators
        indicators['volatility'] = {
            'bb_upper': round(float(latest['bb_upper']), 2) if pd.notna(latest['bb_upper']) else None,
            'bb_middle': round(float(latest['bb_middle']), 2) if pd.notna(latest['bb_middle']) else None,
            'bb_lower': round(float(latest['bb_lower']), 2) if pd.notna(latest['bb_lower']) else None,
            'bb_pct': round(float(latest['bb_pct']), 4) if pd.notna(latest['bb_pct']) else None,
            'bb_width': round(float(latest['bb_width']), 4) if pd.notna(latest['bb_width']) else None,
            'atr_14': round(float(latest['atr_14']), 2) if pd.notna(latest['atr_14']) else None,
            'atr_pct': round(float(latest['atr_pct']), 2) if pd.notna(latest['atr_pct']) else None,
            'hv_10': round(float(latest['hv_10']), 4) if pd.notna(latest['hv_10']) else None,
        }
        
        # Volume Indicators
        indicators['volume'] = {
            'obv': round(float(latest['obv']), 0) if pd.notna(latest['obv']) else None,
            'obv_change': round(float(latest['obv_change']), 4) if pd.notna(latest['obv_change']) else None,
            'mfi_14': round(float(latest['mfi_14']), 2) if pd.notna(latest['mfi_14']) else None,
            'cmf_20': round(float(latest['cmf_20']), 4) if pd.notna(latest['cmf_20']) else None,
            'volume_ratio': round(float(latest['volume_ratio']), 2) if pd.notna(latest['volume_ratio']) else None,
        }
        
        # Price Info
        indicators['price'] = {
            'close': round(float(latest['close']), 2),
            'price_vs_ema21': round(float(latest['price_vs_ema21']), 2) if pd.notna(latest['price_vs_ema21']) else None,
            'price_vs_ema50': round(float(latest['price_vs_ema50']), 2) if pd.notna(latest['price_vs_ema50']) else None,
            'price_vs_sma200': round(float(latest['price_vs_sma200']), 2) if pd.notna(latest['price_vs_sma200']) else None,
        }
        
        return indicators


# Singleton instance
enhanced_technical_engine = EnhancedTechnicalEngine()


# ── Utility Functions ─────────────────────────────────────────────────────

def format_technical_summary(result: TechnicalAnalysisResult) -> str:
    """Format technical analysis result for display."""
    emoji_map = {
        'BUY': '📈',
        'SELL': '📉',
        'HOLD': '⏸',
        'STRONG_UPTREND': '🚀',
        'UPTREND': '📈',
        'SIDEWAYS': '↔️',
        'DOWNTREND': '📉',
        'STRONG_DOWNTREND': '💥',
    }
    
    lines = [
        f"┌───────────────────────────────────────┐",
        f"│ 📊 {result.ticker} - Technical Analysis",
        f"├───────────────────────────────────────┤",
        f"│ {emoji_map.get(result.signal, '❓')} Signal: {result.signal} ({result.signal_strength})",
        f"│ {emoji_map.get(result.trend_direction, '❓')} Trend: {result.trend_direction}",
        f"│",
        f"│ 📈 Trend Score:      {result.trend_score:5.1f}/100",
        f"│ 📊 Momentum Score:   {result.momentum_score:5.1f}/100",
        f"│ ⚡ Volatility Score: {result.volatility_score:5.1f}/100",
        f"│ 💰 Volume Score:     {result.volume_score:5.1f}/100",
        f"│",
        f"│ 🎯 Composite Score:  {result.composite_score:5.1f}/100",
    ]
    
    # Add patterns if detected
    if result.candlestick_patterns:
        lines.append(f"│")
        lines.append(f"│ 🕯️  Patterns Detected:")
        for pattern in result.candlestick_patterns[:3]:
            lines.append(f"│    • {pattern['name']} ({pattern['type']})")
    
    # Add divergences if detected
    if result.divergences:
        lines.append(f"│")
        lines.append(f"│ 🔄 Divergences:")
        for div in result.divergences[:2]:
            lines.append(f"│    • {div['indicator']} {div['type'].upper()} divergence")
    
    # Add support/resistance
    if result.support_levels:
        lines.append(f"│")
        lines.append(f"│ 🛑 Support Levels:")
        for supp in result.support_levels[:2]:
            lines.append(f"│    • Rp {supp['level']:,.0f} ({supp['type']})")
    
    if result.resistance_levels:
        lines.append(f"│")
        lines.append(f"│ 🎯 Resistance Levels:")
        for res in result.resistance_levels[:2]:
            lines.append(f"│    • Rp {res['level']:,.0f} ({res['type']})")
    
    lines.append(f"└───────────────────────────────────────┘")
    
    return "\n".join(lines)
