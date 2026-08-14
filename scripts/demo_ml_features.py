#!/usr/bin/env python3
"""Demo script for ML Features (Ensemble, Foreign Flow, Walk-Forward).

Tests all new ML features:
1. ML Ensemble (XGBoost + LightGBM)
2. Foreign Flow Analysis (Bandar tracking)
3. Walk-Forward Validation

Usage:
    python scripts/demo_ml_features.py
"""

import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
import yfinance as yf

from app.services.ml_ensemble import MLEnsemble, ml_ensemble
from app.services.foreign_flow import ForeignFlowAnalyzer, format_foreign_flow_summary
from app.services.walk_forward import WalkForwardValidator, format_walk_forward_summary


def test_ml_ensemble():
    """Test ML Ensemble prediction."""
    print("\n" + "=" * 80)
    print("🤖 TESTING: ML ENSEMBLE (XGBoost + LightGBM)")
    print("=" * 80)
    
    # Fetch data for training
    print("\n📥 Fetching training data...")
    tickers = ["BBCA", "BBRI", "TLKM", "UNVR", "ASII"]
    all_data = []
    
    for ticker in tickers:
        try:
            stock = yf.Ticker(f"{ticker}.JK")
            df = stock.history(period="2y")
            
            if df.empty:
                continue
            
            df = df.reset_index()
            df.columns = df.columns.str.lower()
            df['ticker'] = ticker
            
            # Create target: 1 if price goes up in next 3 days, 0 otherwise
            df['target'] = (df['close'].shift(-3) > df['close']).astype(int)
            
            # Add basic features
            df['rsi_14'] = 50 + np.random.randn(len(df)) * 10  # Placeholder
            df['macd_histogram'] = np.random.randn(len(df))
            df['volume_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
            
            all_data.append(df)
        
        except Exception as e:
            print(f"  Error fetching {ticker}: {e}")
    
    if not all_data:
        print("❌ No data fetched")
        return None
    
    data = pd.concat(all_data, ignore_index=True)
    print(f"✓ Fetched {len(data)} samples from {len(tickers)} stocks")
    
    # Prepare features
    feature_cols = ['rsi_14', 'macd_histogram', 'volume_ratio']
    X = data[feature_cols].fillna(0)
    y = data['target'].fillna(0)
    
    # Split train/test
    train_size = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:train_size], X.iloc[train_size:]
    y_train, y_test = y.iloc[:train_size], y.iloc[train_size:]
    
    print(f"\n📊 Training data: {len(X_train)} samples")
    print(f"📊 Test data: {len(X_test)} samples")
    
    # Train ensemble
    print("\n⚙️  Training ML Ensemble...")
    ensemble = MLEnsemble(use_stacking=True)
    
    try:
        metrics = ensemble.train(X_train, y_train, X_test, y_test)
        
        print(f"\n✅ Training complete!")
        print(f"   Models: {ensemble.get_models()}")
        print(f"   Accuracy: {metrics.accuracy:.2%}")
        print(f"   F1 Score: {metrics.f1_score:.2%}")
        print(f"   ROC AUC: {metrics.roc_auc:.2f}")
        
        # Test prediction
        print("\n🔮 Testing prediction...")
        sample_features = {
            'rsi_14': 55.0,
            'macd_histogram': 0.5,
            'volume_ratio': 1.5,
            'ma_distance_pct': 2.0,
            'atr_pct': 2.5,
            'price_momentum_5d': 3.0,
            'bb_position': 0.6,
            'adx': 25.0,
            'stoch_k': 60.0,
            'willr_14': -40.0,
            'cci_20': 50.0,
            'roc_10': 2.0,
            'obv_change': 0.05,
            'mfi_14': 55.0,
            'cmf_20': 0.1,
            'revenue_growth_yoy': 0.10,
            'earnings_growth_yoy': 0.15,
            'roe': 0.18,
            'roa': 0.08,
            'debt_to_equity': 0.5,
            'current_ratio': 1.5,
            'pe_ratio': 12.0,
            'pb_ratio': 2.0,
        }
        
        prediction = ensemble.predict_single(sample_features)
        print(f"\n📈 Sample Prediction:")
        print(f"   Direction: {'UP' if prediction.prediction == 1 else 'DOWN'}")
        print(f"   Probability: {prediction.probability:.1%}")
        print(f"   Confidence: {prediction.confidence}")
        print(f"   Models Agreement: {prediction.models_agreement:.1%}")
        
        return ensemble
    
    except Exception as e:
        print(f"❌ Training failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_foreign_flow():
    """Test Foreign Flow Analysis."""
    print("\n" + "=" * 80)
    print("💰 TESTING: FOREIGN FLOW ANALYSIS (Bandar Tracking)")
    print("=" * 80)
    
    test_tickers = ["BBCA", "BBRI", "TLKM"]
    analyzer = ForeignFlowAnalyzer()
    
    results = []
    
    for ticker in test_tickers:
        print(f"\n📊 Analyzing {ticker}...")
        
        try:
            result = analyzer.analyze(ticker, period="3mo")
            
            if result:
                print(format_foreign_flow_summary(result))
                results.append(result)
            else:
                print(f"  ❌ Analysis failed for {ticker}")
        
        except Exception as e:
            print(f"  ❌ Error: {e}")
    
    # Summary
    if results:
        print("\n" + "=" * 80)
        print("📊 FOREIGN FLOW SUMMARY")
        print("=" * 80)
        print(f"{'Ticker':<8} {'Bandar Score':>12} {'Signal':<25} {'Confidence':<10}")
        print("-" * 80)
        
        for r in sorted(results, key=lambda x: -x.bandar_score):
            emoji = "🟢" if r.bandar_score >= 65 else "🟡" if r.bandar_score >= 45 else "🔴"
            print(f"{emoji} {r.ticker:<6} {r.bandar_score:>11.1f} {r.signal:<25} {r.confidence:<10}")
    
    return results


def test_walk_forward():
    """Test Walk-Forward Validation."""
    print("\n" + "=" * 80)
    print("🔄 TESTING: WALK-FORWARD VALIDATION")
    print("=" * 80)
    
    # Create synthetic data for testing
    print("\n📊 Generating synthetic test data...")
    
    np.random.seed(42)
    n_samples = 500
    
    data = pd.DataFrame({
        'date': pd.date_range(start='2024-01-01', periods=n_samples, freq='D'),
        'feature_1': np.random.randn(n_samples),
        'feature_2': np.random.randn(n_samples),
        'feature_3': np.random.randn(n_samples),
        'target': (np.random.randn(n_samples) > 0).astype(int),  # Random target
    })
    
    print(f"✓ Generated {len(data)} samples")
    
    # Create a simple strategy
    from sklearn.ensemble import RandomForestClassifier
    strategy = RandomForestClassifier(n_estimators=50, max_depth=5, random_state=42)
    
    # Run walk-forward validation
    print("\n⚙️  Running walk-forward validation (5 folds)...")
    
    validator = WalkForwardValidator(min_train_size=200, min_test_size=50)
    
    try:
        result = validator.validate(
            strategy=strategy,
            data=data,
            n_splits=5,
            strategy_name="Random Forest Test",
        )
        
        print("\n" + format_walk_forward_summary(result))
        
        return result
    
    except Exception as e:
        print(f"❌ Walk-forward validation failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Main test function."""
    print("\n" + "╔" + "=" * 78 + "╗")
    print("║" + " " * 18 + "IDX AI Stock Assistant - ML Features Demo" + " " * 18 + "║")
    print("╚" + "=" * 78 + "╝")
    print(f"\n📅 Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {
        'ml_ensemble': None,
        'foreign_flow': [],
        'walk_forward': None,
    }
    
    # Test ML Ensemble
    print("\n" + "🚀 " * 20 + "\n")
    results['ml_ensemble'] = test_ml_ensemble()
    
    # Test Foreign Flow
    print("\n" + "💰 " * 20 + "\n")
    results['foreign_flow'] = test_foreign_flow()
    
    # Test Walk-Forward
    print("\n" + "🔄 " * 20 + "\n")
    results['walk_forward'] = test_walk_forward()
    
    # Final Summary
    print("\n" + "=" * 80)
    print("📊 FINAL SUMMARY")
    print("=" * 80)
    
    if results['ml_ensemble']:
        print("✅ ML Ensemble: WORKING")
        models = results['ml_ensemble'].get_models()
        print(f"   Models: {', '.join(models)}")
    else:
        print("❌ ML Ensemble: FAILED")
    
    if results['foreign_flow']:
        print(f"✅ Foreign Flow: WORKING ({len(results['foreign_flow'])} stocks analyzed)")
    else:
        print("❌ Foreign Flow: FAILED")
    
    if results['walk_forward']:
        print("✅ Walk-Forward: WORKING")
        print(f"   Recommendation: {results['walk_forward'].recommendation}")
    else:
        print("❌ Walk-Forward: FAILED")
    
    print("\n" + "=" * 80)
    print("✅ All ML features tested!")
    print("\n📝 Next Steps:")
    print("   1. Install dependencies: pip install xgboost lightgbm shap")
    print("   2. Train ML ensemble on real data")
    print("   3. Integrate foreign flow into scanner")
    print("   4. Validate strategies with walk-forward")
    print()


if __name__ == "__main__":
    main()
