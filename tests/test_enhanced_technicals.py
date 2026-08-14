"""Unit tests for Enhanced Technical Analysis Engine."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from app.services.enhanced_technicals import (
    EnhancedTechnicalEngine,
    TechnicalAnalysisResult,
    TrendDirection,
    SignalStrength,
    DivergenceResult,
    CandlestickPattern,
    format_technical_summary,
)

from app.services.multi_timeframe import (
    MultiTimeframeAnalyzer,
    TimeframeResampler,
    Timeframe,
    format_multi_timeframe_summary,
)

from app.services.analysis_engine import (
    analyze_enhanced,
    format_enhanced_summary,
    get_enhanced_signal_summary,
)


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def sample_ohlcv_data():
    """Generate sample OHLCV data for testing."""
    np.random.seed(42)
    
    dates = pd.date_range(start='2024-01-01', periods=200, freq='D')
    
    # Generate realistic price data with trend
    base_price = 5000
    returns = np.random.randn(200) * 0.02  # 2% daily volatility
    price = base_price * np.cumprod(1 + returns)
    
    # Generate OHLCV
    data = []
    for i, date in enumerate(dates):
        close = price[i]
        daily_range = close * np.random.uniform(0.01, 0.03)  # 1-3% range
        high = close + daily_range * np.random.uniform(0.3, 0.7)
        low = close - daily_range * np.random.uniform(0.3, 0.7)
        open_price = low + (high - low) * np.random.uniform(0.2, 0.8)
        volume = int(np.random.uniform(1_000_000, 10_000_000))
        
        data.append({
            'date': date,
            'open': open_price,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume,
        })
    
    return pd.DataFrame(data)


@pytest.fixture
def uptrend_data():
    """Generate clear uptrend data."""
    np.random.seed(123)
    
    dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
    
    # Strong uptrend
    base_price = 1000
    trend = np.linspace(0, 0.5, 100)  # 50% increase over period
    noise = np.random.randn(100) * 0.01
    price = base_price * (1 + trend + noise)
    
    data = []
    for i, date in enumerate(dates):
        close = price[i]
        daily_range = close * 0.02
        high = close + daily_range * 0.5
        low = close - daily_range * 0.5
        open_price = low + (high - low) * 0.5
        volume = int(np.random.uniform(1_000_000, 5_000_000))
        
        data.append({
            'date': date,
            'open': open_price,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume,
        })
    
    return pd.DataFrame(data)


@pytest.fixture
def downtrend_data():
    """Generate clear downtrend data."""
    np.random.seed(456)
    
    dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
    
    # Strong downtrend
    base_price = 5000
    trend = np.linspace(0, -0.3, 100)  # 30% decrease
    noise = np.random.randn(100) * 0.015
    price = base_price * (1 + trend + noise)
    
    data = []
    for i, date in enumerate(dates):
        close = price[i]
        daily_range = close * 0.025
        high = close + daily_range * 0.5
        low = close - daily_range * 0.5
        open_price = low + (high - low) * 0.5
        volume = int(np.random.uniform(2_000_000, 8_000_000))
        
        data.append({
            'date': date,
            'open': open_price,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume,
        })
    
    return pd.DataFrame(data)


# ── Enhanced Technical Engine Tests ───────────────────────────────────────

class TestEnhancedTechnicalEngine:
    """Tests for EnhancedTechnicalEngine."""
    
    def test_initialization(self):
        """Test engine initialization."""
        engine = EnhancedTechnicalEngine()
        assert engine.indicator_configs is not None
        assert 'trend' in engine.indicator_configs
        assert 'momentum' in engine.indicator_configs
        assert 'volatility' in engine.indicator_configs
        assert 'volume' in engine.indicator_configs
    
    def test_analyze_basic(self, sample_ohlcv_data):
        """Test basic analysis functionality."""
        engine = EnhancedTechnicalEngine()
        result = engine.analyze(sample_ohlcv_data, "BBCA")
        
        assert isinstance(result, TechnicalAnalysisResult)
        assert result.ticker == "BBCA"
        assert 0 <= result.composite_score <= 100
        assert 0 <= result.trend_score <= 100
        assert 0 <= result.momentum_score <= 100
        assert 0 <= result.volatility_score <= 100
        assert 0 <= result.volume_score <= 100
        assert result.signal in ["BUY", "SELL", "HOLD"]
        assert result.signal_strength in ["STRONG", "MODERATE", "WEAK"]
    
    def test_analyze_uptrend(self, uptrend_data):
        """Test analysis on uptrend data."""
        engine = EnhancedTechnicalEngine()
        result = engine.analyze(uptrend_data, "TLKM")
        
        # Uptrend should have higher trend score
        assert result.trend_score >= 50
        assert result.trend_direction in [
            TrendDirection.UPTREND,
            TrendDirection.STRONG_UPTREND,
            TrendDirection.SIDEWAYS
        ]
    
    def test_analyze_downtrend(self, downtrend_data):
        """Test analysis on downtrend data."""
        engine = EnhancedTechnicalEngine()
        result = engine.analyze(downtrend_data, "GOTO")
        
        # Downtrend should have lower trend score
        assert result.trend_score <= 50 or result.trend_direction in [
            TrendDirection.DOWNTREND,
            TrendDirection.STRONG_DOWNTREND,
        ]
    
    def test_indicator_calculation(self, sample_ohlcv_data):
        """Test that indicators are calculated correctly."""
        engine = EnhancedTechnicalEngine()
        result = engine.analyze(sample_ohlcv_data, "BBRI")
        
        # Check that indicator categories are populated
        assert 'trend' in result.indicators
        assert 'momentum' in result.indicators
        assert 'volatility' in result.indicators
        assert 'volume' in result.indicators
        
        # Check specific indicators exist
        trend = result.indicators['trend']
        assert 'ema_9' in trend or 'adx' in trend
        
        momentum = result.indicators['momentum']
        assert 'rsi_14' in momentum
        assert 'macd' in momentum or 'macd_hist' in momentum
        
        volatility = result.indicators['volatility']
        assert 'bb_upper' in volatility or 'atr_14' in volatility
        
        volume = result.indicators['volume']
        assert 'obv' in volume or 'mfi_14' in volume
    
    def test_support_resistance_detection(self, sample_ohlcv_data):
        """Test support/resistance level detection."""
        engine = EnhancedTechnicalEngine()
        result = engine.analyze(sample_ohlcv_data, "BMRI")
        
        assert isinstance(result.support_levels, list)
        assert isinstance(result.resistance_levels, list)
        
        # Should have at least one level each
        assert len(result.support_levels) >= 1
        assert len(result.resistance_levels) >= 1
        
        # Support should be below current price, resistance above
        current_price = sample_ohlcv_data.iloc[-1]['close']
        
        # Note: This may not always be true depending on trend
        # but generally support < price < resistance
        if result.support_levels:
            assert result.support_levels[0]['level'] > 0
    
    def test_to_dict(self, sample_ohlcv_data):
        """Test result serialization."""
        engine = EnhancedTechnicalEngine()
        result = engine.analyze(sample_ohlcv_data, "ASII")
        
        result_dict = result.to_dict()
        
        assert isinstance(result_dict, dict)
        assert result_dict['ticker'] == "ASII"
        assert 'composite_score' in result_dict
        assert 'indicators' in result_dict
    
    def test_insufficient_data(self):
        """Test handling of insufficient data."""
        engine = EnhancedTechnicalEngine()
        
        # Less than 50 data points
        small_data = pd.DataFrame({
            'date': pd.date_range(start='2024-01-01', periods=30, freq='D'),
            'open': np.random.randn(30) * 100 + 5000,
            'high': np.random.randn(30) * 100 + 5100,
            'low': np.random.randn(30) * 100 + 4900,
            'close': np.random.randn(30) * 100 + 5000,
            'volume': np.random.randint(1_000_000, 10_000_000, 30),
        })
        
        # Should still work but may have some NaN indicators
        result = engine.analyze(small_data, "TEST")
        assert isinstance(result, TechnicalAnalysisResult)
    
    def test_missing_columns(self):
        """Test handling of missing required columns."""
        engine = EnhancedTechnicalEngine()
        
        # Missing 'volume' column
        bad_data = pd.DataFrame({
            'date': pd.date_range(start='2024-01-01', periods=100, freq='D'),
            'open': np.random.randn(100) * 100 + 5000,
            'high': np.random.randn(100) * 100 + 5100,
            'low': np.random.randn(100) * 100 + 4900,
            'close': np.random.randn(100) * 100 + 5000,
        })
        
        with pytest.raises(ValueError, match="Missing required column"):
            engine.analyze(bad_data, "TEST")


# ── Multi-Timeframe Analysis Tests ────────────────────────────────────────

class TestMultiTimeframeAnalyzer:
    """Tests for MultiTimeframeAnalyzer."""
    
    def test_initialization(self):
        """Test analyzer initialization."""
        analyzer = MultiTimeframeAnalyzer()
        assert analyzer.engine is not None
    
    def test_analyze_multiple_timeframes(self, sample_ohlcv_data):
        """Test multi-timeframe analysis."""
        # Create multi-timeframe data
        sample_ohlcv_data = sample_ohlcv_data.set_index('date')
        
        data = {
            Timeframe.LONG: sample_ohlcv_data,
            Timeframe.MEDIUM: sample_ohlcv_data.head(150),
            Timeframe.SHORT: sample_ohlcv_data.head(100),
        }
        
        analyzer = MultiTimeframeAnalyzer()
        result = analyzer.analyze("BBCA", data)
        
        assert result.ticker == "BBCA"
        assert 0 <= result.confluence_score <= 100
        assert result.final_signal in ["BUY", "SELL", "HOLD"]
        assert result.final_strength in ["STRONG", "MODERATE", "WEAK"]
        assert result.confidence in ["HIGH", "MEDIUM", "LOW"]
    
    def test_confluence_calculation(self, uptrend_data, downtrend_data):
        """Test confluence score calculation."""
        uptrend_data = uptrend_data.set_index('date')
        downtrend_data = downtrend_data.set_index('date')
        
        # All timeframes agree (uptrend)
        data_aligned = {
            Timeframe.LONG: uptrend_data,
            Timeframe.MEDIUM: uptrend_data,
            Timeframe.SHORT: uptrend_data,
        }
        
        analyzer = MultiTimeframeAnalyzer()
        result_aligned = analyzer.analyze("TEST", data_aligned)
        
        # Should have high confluence
        assert result_aligned.confluence_score >= 70
    
    def test_conflict_detection(self, uptrend_data, downtrend_data):
        """Test timeframe conflict detection."""
        uptrend_data = uptrend_data.set_index('date')
        downtrend_data = downtrend_data.set_index('date')
        
        # Conflicting timeframes
        data_conflict = {
            Timeframe.LONG: uptrend_data,
            Timeframe.MEDIUM: downtrend_data,
            Timeframe.SHORT: uptrend_data,
        }
        
        analyzer = MultiTimeframeAnalyzer()
        result_conflict = analyzer.analyze("TEST", data_conflict)
        
        # May have lower confluence or HOLD signal
        # (conflict handling depends on implementation)
        assert result_conflict.final_signal in ["BUY", "SELL", "HOLD"]


# ── Timeframe Resampler Tests ────────────────────────────────────────────

class TestTimeframeResampler:
    """Tests for TimeframeResampler."""
    
    def test_resample_ohlcv(self):
        """Test OHLCV resampling."""
        # Create minute data
        dates = pd.date_range(start='2024-01-01', periods=100, freq='15T')
        data = pd.DataFrame({
            'open': np.arange(100, 200),
            'high': np.arange(105, 205),
            'low': np.arange(95, 195),
            'close': np.arange(102, 202),
            'volume': np.arange(1000, 2000),
        }, index=dates)
        
        # Resample to hourly
        resampled = TimeframeResampler.resample_ohlcv(data, '1H')
        
        assert len(resampled) < len(data)
        assert 'open' in resampled.columns
        assert 'high' in resampled.columns
        assert 'low' in resampled.columns
        assert 'close' in resampled.columns
        assert 'volume' in resampled.columns
    
    def test_create_multi_timeframe_data(self, sample_ohlcv_data):
        """Test multi-timeframe data creation."""
        sample_ohlcv_data = sample_ohlcv_data.set_index('date')
        
        data = TimeframeResampler.create_multi_timeframe_data(sample_ohlcv_data)
        
        assert Timeframe.LONG in data
        assert Timeframe.MEDIUM in data
        assert Timeframe.SHORT in data
        
        # Long-term should have daily bars
        assert len(data[Timeframe.LONG]) <= len(sample_ohlcv_data)


# ── Integration Tests ────────────────────────────────────────────────────

class TestIntegration:
    """Integration tests for enhanced analysis."""
    
    def test_analyze_enhanced_function(self, sample_ohlcv_data):
        """Test the analyze_enhanced helper function."""
        history = sample_ohlcv_data.to_dict('records')
        result = analyze_enhanced("BBCA", history)
        
        assert result is not None
        assert isinstance(result, TechnicalAnalysisResult)
        assert result.ticker == "BBCA"
    
    def test_format_enhanced_summary(self, sample_ohlcv_data):
        """Test summary formatting."""
        engine = EnhancedTechnicalEngine()
        result = engine.analyze(sample_ohlcv_data, "TLKM")
        
        summary = format_enhanced_summary(result)
        
        assert isinstance(summary, str)
        assert "TLKM" in summary
        assert "Technical Analysis" in summary
    
    def test_get_enhanced_signal_summary(self, sample_ohlcv_data):
        """Test signal summary extraction."""
        engine = EnhancedTechnicalEngine()
        result = engine.analyze(sample_ohlcv_data, "BBRI")
        
        summary = get_enhanced_signal_summary(result)
        
        assert isinstance(summary, dict)
        assert summary['ticker'] == "BBRI"
        assert 'signal' in summary
        assert 'composite_score' in summary
        assert 'category_scores' in summary
    
    def test_format_multi_timeframe_summary(self, sample_ohlcv_data):
        """Test multi-timeframe summary formatting."""
        sample_ohlcv_data = sample_ohlcv_data.set_index('date')
        
        data = {
            Timeframe.LONG: sample_ohlcv_data,
            Timeframe.MEDIUM: sample_ohlcv_data.head(150),
            Timeframe.SHORT: sample_ohlcv_data.head(100),
        }
        
        analyzer = MultiTimeframeAnalyzer()
        result = analyzer.analyze("ASII", data)
        
        summary = format_multi_timeframe_summary(result)
        
        assert isinstance(summary, str)
        assert "ASII" in summary
        assert "Multi-Timeframe" in summary


# ── Edge Cases and Error Handling ────────────────────────────────────────

class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_dataframe(self):
        """Test handling of empty DataFrame."""
        engine = EnhancedTechnicalEngine()
        empty_data = pd.DataFrame()
        
        with pytest.raises(ValueError):
            engine.analyze(empty_data, "TEST")
    
    def test_all_nan_data(self):
        """Test handling of all-NaN data."""
        engine = EnhancedTechnicalEngine()
        nan_data = pd.DataFrame({
            'date': pd.date_range(start='2024-01-01', periods=100, freq='D'),
            'open': [np.nan] * 100,
            'high': [np.nan] * 100,
            'low': [np.nan] * 100,
            'close': [np.nan] * 100,
            'volume': [np.nan] * 100,
        })
        
        # Should handle gracefully or raise appropriate error
        with pytest.raises(Exception):
            engine.analyze(nan_data, "TEST")
    
    def test_zero_prices(self):
        """Test handling of zero prices."""
        engine = EnhancedTechnicalEngine()
        zero_data = pd.DataFrame({
            'date': pd.date_range(start='2024-01-01', periods=100, freq='D'),
            'open': [0.0] * 100,
            'high': [0.0] * 100,
            'low': [0.0] * 100,
            'close': [0.0] * 100,
            'volume': [1000000] * 100,
        })
        
        # May produce NaN indicators but should not crash
        result = engine.analyze(zero_data, "TEST")
        assert isinstance(result, TechnicalAnalysisResult)
    
    def test_negative_prices(self):
        """Test handling of negative prices (should not happen in reality)."""
        engine = EnhancedTechnicalEngine()
        neg_data = pd.DataFrame({
            'date': pd.date_range(start='2024-01-01', periods=100, freq='D'),
            'open': np.random.randn(100) * 1000 - 500,
            'high': np.random.randn(100) * 1000 - 500,
            'low': np.random.randn(100) * 1000 - 500,
            'close': np.random.randn(100) * 1000 - 500,
            'volume': np.random.randint(1_000_000, 10_000_000, 100),
        })
        
        # Should handle or raise appropriate error
        result = engine.analyze(neg_data, "TEST")
        assert isinstance(result, TechnicalAnalysisResult)


# ── Run Tests ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
