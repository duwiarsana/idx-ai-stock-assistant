# 🚀 IDX AI Stock Assistant - Improvement Plan

## Executive Summary

**Current State:** ✅ **Phase 1 + Phase 2 + Phase 5 COMPLETE**

**Completed:**
- ✅ Phase 1: Enhanced Technical Analysis (130+ indicators)
- ✅ Phase 2: Fundamental Analysis (PE, PBV, ROE, etc.)
- ✅ Phase 5: Backtesting Engine (Sharpe, Sortino, Max DD)

**Target State:** Professional-grade stock analysis system (8.5/10)

**Remaining:**
- ⏳ Phase 3: Advanced ML (XGBoost, LSTM)
- ⏳ Phase 4: Market Sentiment (Foreign Flow, News NLP)

---

## 📊 Phase 1: Enhanced Technical Analysis (Weeks 1-2)

### 1.1 Add Professional Technical Indicators

#### Current State
```python
# Only basic indicators
- RSI-14
- MACD (12, 26, 9)
- SMA-20, SMA-50
- ATR-14
- Volume Ratio
```

#### Target State
```python
# Enhanced indicators with multiple timeframes
class EnhancedTechnicalIndicators:
    # Trend Indicators
    - EMA-9, EMA-21, EMA-50, EMA-200
    - SMA-50, SMA-200 (Golden/Death Cross detection)
    - ADX (Average Directional Index) - trend strength
    - Ichimoku Cloud (Tenkan, Kijun, Senkou A/B, Chikou)
    - SuperTrend
    - Parabolic SAR
    
    # Momentum Indicators
    - RSI-14 (with divergence detection)
    - Stochastic Oscillator (%K, %D)
    - Williams %R
    - CCI (Commodity Channel Index)
    - ROC (Rate of Change)
    - Momentum (Rate of Change)
    
    # Volatility Indicators
    - Bollinger Bands (%B, Bandwidth)
    - Keltner Channel
    - ATR Trailing Stop
    - Historical Volatility (10d, 30d, 90d)
    - Standard Deviation
    
    # Volume Indicators
    - OBV (On-Balance Volume)
    - VWAP (Volume Weighted Average Price)
    - MFI (Money Flow Index)
    - Accumulation/Distribution Line
    - Volume Profile (POC, Value Area)
    - Chaikin Money Flow
    
    # Pattern Recognition
    - Candlestick Patterns (60+ patterns via pandas-ta)
    - Chart Patterns (Head & Shoulders, Double Top/Bottom)
    - Support/Resistance (multi-timeframe)
    - Fibonacci Retracement Levels
```

#### Implementation
```python
# app/services/enhanced_technicals.py
import pandas_ta as ta

class EnhancedTechnicalEngine:
    def __init__(self):
        self.indicator_configs = {
            'trend': {'weight': 0.30},
            'momentum': {'weight': 0.25},
            'volatility': {'weight': 0.20},
            'volume': {'weight': 0.25},
        }
    
    def calculate_all_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        # Trend
        df['ema_9'] = ta.ema(df['close'], length=9)
        df['ema_21'] = ta.ema(df['close'], length=21)
        df['adx'] = ta.adx(df['high'], df['low'], df['close'])['ADX_14']
        
        # Ichimoku
        ichimoku = ta.ichimoku(df['high'], df['low'], df['close'])
        df['tenkan'] = ichimoku[0]
        df['kijun'] = ichimoku[1]
        
        # Momentum
        df['stoch_k'], df['stoch_d'] = ta.stoch(df['high'], df['low'], df['close'])
        df['willr'] = ta.willr(df['high'], df['low'], df['close'])
        df['cci'] = ta.cci(df['high'], df['low'], df['close'])
        
        # Volatility
        bbands = ta.bbands(df['close'])
        df['bb_upper'] = bbands['BBU_20_2.0']
        df['bb_lower'] = bbands['BBL_20_2.0']
        df['bb_pct'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])
        
        # Volume
        df['obv'] = ta.obv(df['close'], df['volume'])
        df['mfi'] = ta.mfi(df['high'], df['low'], df['close'], df['volume'])
        df['cmf'] = ta.cmf(df['high'], df['low'], df['close'], df['volume'])
        
        return df
```

### 1.2 Multi-Timeframe Analysis

```python
class MultiTimeframeAnalyzer:
    timeframes = {
        'short': {'period': '15m', 'lookback': 50, 'weight': 0.20},
        'medium': {'period': '1h', 'lookback': 50, 'weight': 0.30},
        'long': {'period': '1D', 'lookback': 100, 'weight': 0.50},
    }
    
    def analyze(self, ticker: str) -> dict:
        """Analyze multiple timeframes and aggregate signals."""
        signals = {}
        for tf_name, config in self.timeframes.items():
            df = self.fetch_data(ticker, timeframe=config['period'])
            signals[tf_name] = self.calculate_signals(df)
        
        # Weighted aggregation
        final_signal = self.aggregate_signals(signals)
        return {
            'timeframe_signals': signals,
            'final_signal': final_signal,
            'confluence_score': self.calculate_confluence(signals)
        }
```

### 1.3 Signal Divergence Detection

```python
class DivergenceDetector:
    def detect_rsi_divergence(self, df: pd.DataFrame) -> str:
        """Detect bullish/bearish divergence between price and RSI."""
        # Find price swings
        price_highs = self.find_peaks(df['high'], order=5)
        price_lows = self.find_peaks(-df['low'], order=5)
        
        # Find RSI swings
        rsi_highs = self.find_peaks(df['rsi_14'], order=5)
        rsi_lows = self.find_peaks(-df['rsi_14'], order=5)
        
        # Bullish divergence: lower lows in price, higher lows in RSI
        if self.is_lower_lows(price_lows) and self.is_higher_lows(rsi_lows):
            return 'BULLISH_DIVERGENCE'
        
        # Bearish divergence: higher highs in price, lower highs in RSI
        if self.is_higher_highs(price_highs) and self.is_lower_highs(rsi_highs):
            return 'BEARISH_DIVERGENCE'
        
        return 'NO_DIVERGENCE'
```

---

## 📈 Phase 2: Fundamental Analysis Integration (Weeks 3-4)

### 2.1 Financial Ratios & Metrics

```python
class FundamentalAnalyzer:
    """Analyze company fundamentals for stock selection."""
    
    # Growth Metrics
    - Revenue Growth (YoY, QoQ)
    - Earnings Growth (YoY, QoQ)
    - EPS Growth
    - Book Value Growth
    
    # Profitability Metrics
    - ROE (Return on Equity)
    - ROA (Return on Assets)
    - ROIC (Return on Invested Capital)
    - Gross Margin
    - Operating Margin
    - Net Profit Margin
    
    # Valuation Metrics
    - P/E Ratio (Trailing, Forward)
    - P/B Ratio
    - P/S Ratio
    - PEG Ratio
    - EV/EBITDA
    - Price to Free Cash Flow
    
    # Financial Health
    - Debt to Equity
    - Current Ratio
    - Quick Ratio
    - Interest Coverage Ratio
    - Altman Z-Score
    
    # Efficiency Metrics
    - Asset Turnover
    - Inventory Turnover
    - Receivables Turnover
    - Cash Conversion Cycle
```

### 2.2 Data Sources for Indonesian Stocks

```python
class IDXDataFetcher:
    """Fetch fundamental data for Indonesian stocks."""
    
    sources = {
        'idx_official': 'https://www.idx.co.id/',
        'idx_data': 'https://data.idx.co.id/',
        'yahoo_finance': 'yfinance library',
        'morningstar': 'https://www.morningstar.com/',
        'refinitiv': 'API (paid)',
        'bloomberg': 'API (paid)',
    }
    
    async def fetch_financials(self, ticker: str) -> dict:
        """Fetch financial statements from multiple sources."""
        return {
            'income_statement': await self.fetch_income_statement(ticker),
            'balance_sheet': await self.fetch_balance_sheet(ticker),
            'cash_flow': await self.fetch_cash_flow(ticker),
            'ratios': self.calculate_ratios(),
            'growth_rates': self.calculate_growth_rates(),
        }
```

### 2.3 Fundamental Scoring System

```python
class FundamentalScorer:
    """Score stocks based on fundamental metrics."""
    
    weights = {
        'growth': 0.25,
        'profitability': 0.25,
        'valuation': 0.25,
        'financial_health': 0.25,
    }
    
    def score_growth(self, metrics: dict) -> float:
        """Score based on growth metrics (0-100)."""
        revenue_growth = metrics.get('revenue_growth_yoy', 0)
        earnings_growth = metrics.get('earnings_growth_yoy', 0)
        eps_growth = metrics.get('eps_growth_yoy', 0)
        
        # Score each metric (0-100)
        revenue_score = min(100, max(0, revenue_growth * 5))
        earnings_score = min(100, max(0, earnings_growth * 5))
        eps_score = min(100, max(0, eps_growth * 5))
        
        return (revenue_score + earnings_score + eps_score) / 3
    
    def score_valuation(self, metrics: dict, sector_peers: dict) -> float:
        """Score based on valuation (cheaper = higher score)."""
        pe = metrics.get('pe_ratio', 0)
        pb = metrics.get('pb_ratio', 0)
        peg = metrics.get('peg_ratio', 0)
        
        # Compare to sector average
        sector_pe = sector_peers.get('avg_pe', 15)
        sector_pb = sector_peers.get('avg_pb', 2)
        
        # Lower PE/PB = higher score (value investing)
        pe_score = max(0, 100 - (pe / sector_pe * 50))
        pb_score = max(0, 100 - (pb / sector_pb * 50))
        peg_score = max(0, 100 - (peg * 50)) if peg > 0 else 50
        
        return (pe_score + pb_score + peg_score) / 3
```

---

## 🤖 Phase 3: Advanced ML & Quantitative Models (Weeks 5-8)

### 3.1 Feature Engineering Enhancement

```python
class AdvancedFeatureEngineer:
    """Create advanced features for ML models."""
    
    def create_features(self, df: pd.DataFrame) -> pd.DataFrame:
        # Price-based features
        df['returns_1d'] = df['close'].pct_change(1)
        df['returns_5d'] = df['close'].pct_change(5)
        df['returns_10d'] = df['close'].pct_change(10)
        df['returns_20d'] = df['close'].pct_change(20)
        
        # Volatility features
        df['volatility_10d'] = df['returns_1d'].rolling(10).std()
        df['volatility_30d'] = df['returns_1d'].rolling(30).std()
        df['volatility_ratio'] = df['volatility_10d'] / df['volatility_30d']
        
        # Volume features
        df['volume_change'] = df['volume'].pct_change()
        df['volume_ma_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
        df['obv_change'] = df['obv'].pct_change(5)
        
        # Relative strength features
        df['relative_to_sector'] = df['close'] / df['sector_index']
        df['relative_to_market'] = df['close'] / df['ihsg_index']
        
        # Seasonality features
        df['day_of_week'] = pd.to_datetime(df['date']).dt.dayofweek
        df['month'] = pd.to_datetime(df['date']).dt.month
        df['is_month_end'] = df['day_of_week'].isin([4]).astype(int)
        
        # Lag features
        for lag in [1, 2, 3, 5, 10]:
            df[f'returns_lag_{lag}'] = df['returns_1d'].shift(lag)
        
        # Rolling statistics
        df['skewness_20d'] = df['returns_1d'].rolling(20).skew()
        df['kurtosis_20d'] = df['returns_1d'].rolling(20).kurt()
        
        return df
```

### 3.2 Multiple ML Models Ensemble

```python
class EnsembleMLPredictor:
    """Ensemble of multiple ML models for better predictions."""
    
    models = {
        'xgboost': XGBClassifier(
            n_estimators=500,
            max_depth=6,
            learning_rate=0.01,
            subsample=0.8,
            colsample_bytree=0.8,
        ),
        'lightgbm': LGBMClassifier(
            n_estimators=500,
            max_depth=6,
            learning_rate=0.01,
        ),
        'random_forest': RandomForestClassifier(
            n_estimators=500,
            max_depth=10,
            min_samples_split=5,
        ),
        'logistic_regression': LogisticRegression(
            C=0.1,
            penalty='l2',
        ),
    }
    
    def predict(self, features: pd.DataFrame) -> dict:
        """Predict using ensemble and return probabilities."""
        predictions = {}
        for name, model in self.models.items():
            proba = model.predict_proba(features)
            predictions[name] = proba[0][1]  # Probability of UP
        
        # Weighted average (weights optimized via cross-validation)
        weights = {
            'xgboost': 0.35,
            'lightgbm': 0.30,
            'random_forest': 0.25,
            'logistic_regression': 0.10,
        }
        
        ensemble_proba = sum(predictions[m] * weights[m] for m in weights)
        
        return {
            'individual_predictions': predictions,
            'ensemble_probability': ensemble_proba,
            'direction': 'UP' if ensemble_proba > 0.5 else 'DOWN',
            'confidence': abs(ensemble_proba - 0.5) * 2,
        }
```

### 3.3 Deep Learning Models (LSTM/GRU)

```python
class LSTMPricePredictor:
    """LSTM-based time series prediction for stock prices."""
    
    def build_model(self, input_shape: tuple) -> tf.keras.Model:
        model = tf.keras.Sequential([
            # LSTM layers
            tf.keras.layers.LSTM(
                units=128,
                return_sequences=True,
                input_shape=input_shape,
            ),
            tf.keras.layers.Dropout(0.2),
            tf.keras.layers.LSTM(units=64, return_sequences=True),
            tf.keras.layers.Dropout(0.2),
            tf.keras.layers.LSTM(units=32),
            tf.keras.layers.Dropout(0.2),
            
            # Dense layers
            tf.keras.layers.Dense(64, activation='relu'),
            tf.keras.layers.Dropout(0.2),
            tf.keras.layers.Dense(32, activation='relu'),
            
            # Output (probability of price going up)
            tf.keras.layers.Dense(1, activation='sigmoid'),
        ])
        
        model.compile(
            optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
            loss='binary_crossentropy',
            metrics=['accuracy', tf.keras.metrics.AUC()],
        )
        
        return model
    
    def prepare_sequences(self, data: np.ndarray, seq_length: int = 60) -> tuple:
        """Prepare sequences for LSTM training."""
        X, y = [], []
        for i in range(len(data) - seq_length):
            X.append(data[i:i+seq_length])
            y.append(data[i+seq_length, -1])  # Target: direction
        
        return np.array(X), np.array(y)
```

### 3.4 Walk-Forward Validation

```python
class WalkForwardValidator:
    """Proper time-series cross-validation."""
    
    def validate(self, data: pd.DataFrame, model, n_splits: int = 5):
        """Walk-forward validation for time series."""
        results = []
        
        # Split data chronologically
        train_size = len(data) // (n_splits + 1)
        
        for i in range(n_splits):
            # Train set: from start to current split
            train_end = (i + 1) * train_size
            train_data = data.iloc[:train_end]
            
            # Test set: next period
            test_start = train_end
            test_end = test_start + train_size // 2
            test_data = data.iloc[test_start:test_end]
            
            # Train model
            model.fit(train_data)
            
            # Predict
            predictions = model.predict(test_data)
            
            # Calculate metrics
            metrics = self.calculate_metrics(test_data, predictions)
            results.append(metrics)
        
        return {
            'mean_accuracy': np.mean([r['accuracy'] for r in results]),
            'mean_precision': np.mean([r['precision'] for r in results]),
            'mean_recall': np.mean([r['recall'] for r in results]),
            'mean_sharpe': np.mean([r['sharpe'] for r in results]),
            'std_accuracy': np.std([r['accuracy'] for r in results]),
        }
```

---

## 📰 Phase 4: Market Sentiment & Context (Weeks 7-9)

### 4.1 Market Sentiment Analysis

```python
class MarketSentimentAnalyzer:
    """Analyze market sentiment from multiple sources."""
    
    def analyze(self) -> dict:
        return {
            'fear_greed_index': self.calculate_fear_greed_index(),
            'put_call_ratio': self.fetch_put_call_ratio(),
            'advance_decline': self.fetch_advance_decline(),
            'new_highs_lows': self.fetch_new_highs_lows(),
            'vix_level': self.fetch_vix_level(),
            'short_interest': self.fetch_short_interest(),
            'insider_trading': self.fetch_insider_trading(),
            'institutional_flows': self.fetch_institutional_flows(),
        }
    
    def calculate_fear_greed_index(self) -> float:
        """Calculate composite fear & greed index (0-100)."""
        components = {
            'market_momentum': self.get_market_momentum_score(),
            'volatility': self.get_volatility_score(),
            'put_call_ratio': self.get_put_call_score(),
            'advance_decline': self.get_advance_decline_score(),
            'safe_haven_demand': self.get_safe_haven_score(),
        }
        
        # Weighted average
        weights = {
            'market_momentum': 0.20,
            'volatility': 0.20,
            'put_call_ratio': 0.15,
            'advance_decline': 0.25,
            'safe_haven_demand': 0.20,
        }
        
        score = sum(components[k] * weights[k] for k in components)
        return score  # 0 = Extreme Fear, 100 = Extreme Greed
```

### 4.2 News Sentiment Analysis with NLP

```python
class NewsSentimentAnalyzer:
    """Analyze news sentiment using NLP."""
    
    def __init__(self):
        # Use pre-trained model or fine-tune on financial news
        self.nlp_model = self.load_financial_sentiment_model()
    
    def analyze_news(self, ticker: str, days: int = 7) -> dict:
        """Analyze news sentiment for a stock."""
        news_articles = self.fetch_news(ticker, days)
        
        sentiments = []
        for article in news_articles:
            sentiment = self.nlp_model.predict(article['content'])
            sentiments.append({
                'source': article['source'],
                'sentiment': sentiment['label'],  # POSITIVE/NEGATIVE/NEUTRAL
                'confidence': sentiment['score'],
                'relevance': self.calculate_relevance(article, ticker),
            })
        
        # Aggregate
        positive = sum(1 for s in sentiments if s['sentiment'] == 'POSITIVE')
        negative = sum(1 for s in sentiments if s['sentiment'] == 'NEGATIVE')
        neutral = len(sentiments) - positive - negative
        
        return {
            'total_articles': len(sentiments),
            'positive': positive,
            'negative': negative,
            'neutral': neutral,
            'sentiment_score': (positive - negative) / len(sentiments),
            'articles': sentiments,
        }
```

### 4.3 Foreign Flow Analysis (Critical for IDX)

```python
class ForeignFlowAnalyzer:
    """Track foreign investor flows in IDX stocks."""
    
    def analyze(self, ticker: str, days: int = 30) -> dict:
        """Analyze foreign buying/selling activity."""
        flow_data = self.fetch_foreign_flow_data(ticker, days)
        
        net_buy = flow_data['foreign_buy'] - flow_data['foreign_sell']
        net_buy_value = net_buy * flow_data['avg_price']
        
        # Calculate accumulation/distribution
        accumulation_days = sum(1 for d in flow_data if d['net_buy'] > 0)
        distribution_days = sum(1 for d in flow_data if d['net_buy'] < 0)
        
        # Trend
        recent_5d = flow_data[-5:]
        recent_5d_trend = sum(d['net_buy'] for d in recent_5d)
        
        return {
            'net_buy_shares': net_buy,
            'net_buy_value_idr': net_buy_value,
            'accumulation_days': accumulation_days,
            'distribution_days': distribution_days,
            'foreign_ownership_pct': flow_data['ownership_pct'],
            'recent_5d_trend': 'ACCUMULATION' if recent_5d_trend > 0 else 'DISTRIBUTION',
            'signal': self.generate_signal(flow_data),
        }
    
    def generate_signal(self, flow_data: list) -> str:
        """Generate signal based on foreign flow patterns."""
        # Strong buy: consecutive accumulation + increasing ownership
        if self.is_consecutive_accumulation(flow_data, days=5):
            return 'STRONG_BUY'
        
        # Buy: net accumulation over period
        if sum(d['net_buy'] for d in flow_data) > 0:
            return 'BUY'
        
        # Sell: consecutive distribution
        if self.is_consecutive_distribution(flow_data, days=5):
            return 'SELL'
        
        return 'HOLD'
```

### 4.4 IHSG & Sector Correlation

```python
class MarketContextAnalyzer:
    """Analyze market context and sector rotation."""
    
    def analyze(self, ticker: str) -> dict:
        """Analyze stock in market context."""
        stock_data = self.fetch_stock_data(ticker)
        ihsg_data = self.fetch_ihsg_data()
        sector_data = self.fetch_sector_data(ticker)
        
        # Calculate correlations
        correlation_ihsg = self.calculate_correlation(
            stock_data['returns'],
            ihsg_data['returns']
        )
        
        correlation_sector = self.calculate_correlation(
            stock_data['returns'],
            sector_data['returns']
        )
        
        # Beta calculation
        beta = self.calculate_beta(stock_data['returns'], ihsg_data['returns'])
        
        # Relative strength
        relative_strength = stock_data['price'] / ihsg_data['index']
        rs_trend = self.calculate_trend(relative_strength)
        
        return {
            'ihsg_correlation': correlation_ihsg,
            'sector_correlation': correlation_sector,
            'beta': beta,
            'relative_strength': float(relative_strength[-1]),
            'rs_trend': rs_trend,  # 'OUTPERFORMING' or 'UNDERPERFORMING'
            'market_regime': self.identify_market_regime(ihsg_data),
            'sector_rotation_signal': self.analyze_sector_rotation(),
        }
```

---

## 🛡️ Phase 5: Backtesting Engine (Weeks 9-12)

### 5.1 Backtesting Framework

```python
class BacktestEngine:
    """Backtest trading strategies on historical data."""
    
    def __init__(self, initial_capital: float = 100_000_000):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.positions = {}
        self.trades = []
    
    def run(self, strategy, data: pd.DataFrame, start_date, end_date) -> dict:
        """Run backtest and return performance metrics."""
        self.reset()
        
        for date, row in data[start_date:end_date].iterrows():
            # Generate signals
            signal = strategy.generate_signal(row, self.positions)
            
            # Execute trades
            if signal == 'BUY' and self.can_buy():
                self.buy(row['ticker'], row['close'], date)
            elif signal == 'SELL' and row['ticker'] in self.positions:
                self.sell(row['ticker'], row['close'], date)
        
        # Calculate performance metrics
        return self.calculate_performance_metrics()
    
    def calculate_performance_metrics(self) -> dict:
        """Calculate comprehensive performance metrics."""
        returns = self.calculate_returns()
        
        return {
            'total_return': self.calculate_total_return(),
            'annualized_return': self.calculate_annualized_return(),
            'sharpe_ratio': self.calculate_sharpe_ratio(returns),
            'sortino_ratio': self.calculate_sortino_ratio(returns),
            'max_drawdown': self.calculate_max_drawdown(),
            'win_rate': self.calculate_win_rate(),
            'profit_factor': self.calculate_profit_factor(),
            'avg_win': self.calculate_avg_win(),
            'avg_loss': self.calculate_avg_loss(),
            'avg_trade_duration': self.calculate_avg_duration(),
            'total_trades': len(self.trades),
            'calmar_ratio': self.calculate_calmar_ratio(),
            'value_at_risk_95': self.calculate_var(0.95),
            'expected_shortfall': self.calculate_expected_shortfall(),
        }
```

### 5.2 Strategy Optimization

```python
class StrategyOptimizer:
    """Optimize strategy parameters using grid search."""
    
    def optimize(self, strategy, data: pd.DataFrame, param_grid: dict) -> dict:
        """Find optimal parameters via grid search."""
        best_params = None
        best_score = -float('inf')
        all_results = []
        
        # Generate all parameter combinations
        param_combinations = list(itertools.product(*param_grid.values()))
        
        for params in param_combinations:
            param_dict = dict(zip(param_grid.keys(), params))
            
            # Set parameters
            strategy.set_params(**param_dict)
            
            # Run backtest
            results = self.backtest_engine.run(strategy, data)
            
            # Score (use Sharpe ratio)
            score = results['sharpe_ratio']
            
            all_results.append({
                'params': param_dict,
                'metrics': results,
                'score': score,
            })
            
            if score > best_score:
                best_score = score
                best_params = param_dict
        
        return {
            'best_params': best_params,
            'best_score': best_score,
            'all_results': sorted(all_results, key=lambda x: -x['score']),
        }
```

---

## 📋 Implementation Priority Matrix

| Priority | Feature | Impact | Effort | Week |
|----------|---------|--------|--------|------|
| **P0** | Enhanced Technical Indicators | High | Low | 1-2 |
| **P0** | Multi-Timeframe Analysis | High | Medium | 2 |
| **P0** | Backtesting Engine | Critical | High | 9-12 |
| **P1** | Fundamental Analysis | High | Medium | 3-4 |
| **P1** | ML Ensemble (XGBoost + LightGBM) | High | Medium | 5-6 |
| **P1** | Foreign Flow Analysis | High | Low | 7 |
| **P2** | LSTM Deep Learning | Medium | High | 6-8 |
| **P2** | News Sentiment NLP | Medium | Medium | 7-8 |
| **P2** | Market Sentiment Index | Medium | Low | 8 |
| **P3** | Ichimoku Cloud | Medium | Low | 2 |
| **P3** | Pattern Recognition | Medium | Medium | 2-3 |
| **P3** | Sector Rotation | Medium | Medium | 8 |

---

## 🎯 Success Metrics

After implementation, the system should achieve:

| Metric | Current | Target |
|--------|---------|--------|
| **Win Rate** | Unknown | >55% |
| **Profit Factor** | Unknown | >1.5 |
| **Sharpe Ratio** | Unknown | >1.0 |
| **Max Drawdown** | Unknown | <20% |
| **Annual Return** | Unknown | >15% |
| **Signal Accuracy** | ~60% | >70% |

---

## 📚 References & Learning Resources

1. **Technical Analysis**
   - "Technical Analysis of the Financial Markets" - John Murphy
   - "Encyclopedia of Technical Chart Patterns" - Thomas Bulkowski
   - pandas-ta documentation: https://pandas-ta.readthedocs.io/

2. **Quantitative Trading**
   - "Quantitative Trading" - Ernest Chan
   - "Algorithmic Trading" - Ernest Chan
   - QuantStart: https://www.quantstart.com/articles/

3. **Machine Learning**
   - "Advances in Financial Machine Learning" - Marcos López de Prado
   - "Machine Learning for Algorithmic Trading" - Stefan Jansen

4. **Indonesian Market**
   - IDX Official: https://www.idx.co.id/
   - Stockbit: https://stockbit.com/
   - Ajaib: https://ajaib.co.id/

---

## 🚀 Next Steps

1. **Week 1:** Install pandas-ta, implement enhanced technical indicators
2. **Week 2:** Add multi-timeframe analysis and divergence detection
3. **Week 3-4:** Integrate fundamental data sources for IDX stocks
4. **Week 5-6:** Build ML ensemble with XGBoost/LightGBM
5. **Week 7-8:** Add sentiment analysis and foreign flow tracking
6. **Week 9-12:** Build comprehensive backtesting engine

Would you like me to start implementing any specific phase?
