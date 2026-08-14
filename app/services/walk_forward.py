"""Walk-Forward Validation - Robust Strategy Testing.

Implements walk-forward analysis to validate trading strategies on 
out-of-sample data, ensuring robustness and preventing overfitting.

Features:
- Rolling window backtest
- Out-of-sample testing
- Strategy stability metrics
- Parameter robustness check
- Performance degradation analysis

Usage:
    from app.services.walk_forward import WalkForwardValidator
    
    validator = WalkForwardValidator()
    results = validator.validate(strategy, data, n_splits=5)
    
    print(f"Out-of-sample Accuracy: {results['oos_accuracy']:.2%}")
    print(f"Strategy Stability: {results['stability_score']:.2f}")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Optional, Callable
from datetime import date

import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit

logger = logging.getLogger(__name__)


# ── Data Classes ───────────────────────────────────────────────────────────

@dataclass
class FoldResult:
    """Result from a single walk-forward fold."""
    fold: int
    train_start: date
    train_end: date
    test_start: date
    test_end: date
    train_samples: int
    test_samples: int
    
    # Performance metrics
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    roc_auc: float
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class WalkForwardResult:
    """Complete walk-forward validation result."""
    # Configuration
    n_splits: int
    strategy_name: str
    ticker: str
    
    # In-sample performance (average)
    is_accuracy: float
    is_precision: float
    is_recall: float
    is_f1: float
    is_roc_auc: float
    is_sharpe: float
    is_return: float
    
    # Out-of-sample performance (average)
    oos_accuracy: float
    oos_precision: float
    oos_recall: float
    oos_f1: float
    oos_roc_auc: float
    oos_sharpe: float
    oos_return: float
    
    # Stability metrics
    accuracy_std: float
    return_std: float
    sharpe_std: float
    stability_score: float  # 0-100
    
    # Performance degradation
    accuracy_degradation: float  # IS - OOS
    return_degradation: float
    sharpe_degradation: float
    
    # Recommendation
    is_robust: bool
    recommendation: str
    
    # Individual fold results
    fold_results: list = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return asdict(self)


# ── Walk-Forward Validator ────────────────────────────────────────────────

class WalkForwardValidator:
    """Walk-forward validation for trading strategies."""
    
    def __init__(self, min_train_size: int = 100, min_test_size: int = 20):
        self.min_train_size = min_train_size
        self.min_test_size = min_test_size
    
    def validate(
        self,
        strategy,
        data: pd.DataFrame,
        n_splits: int = 5,
        strategy_name: str = "Unknown",
    ) -> WalkForwardResult:
        """Perform walk-forward validation.
        
        Parameters
        ----------
        strategy
            Trading strategy or ML model with fit/predict methods
        data : pd.DataFrame
            Historical data with features and target
        n_splits : int
            Number of walk-forward splits
        strategy_name : str
            Name of the strategy
        
        Returns
        -------
        WalkForwardResult
            Validation results
        """
        logger.info(f"Starting walk-forward validation: {n_splits} splits")
        
        # Prepare data
        if 'target' not in data.columns:
            raise ValueError("Data must contain 'target' column")
        
        # Remove rows with NaN target
        data = data.dropna(subset=['target'])
        
        if len(data) < self.min_train_size + self.min_test_size:
            raise ValueError(
                f"Insufficient data: {len(data)} samples. "
                f"Need at least {self.min_train_size + self.min_test_size}"
            )
        
        # Create time series splits
        tscv = TimeSeriesSplit(
            n_splits=n_splits,
            test_size=self.min_test_size,
            gap=0,
        )
        
        fold_results = []
        is_metrics = []
        oos_metrics = []
        
        # Iterate through folds
        for fold, (train_idx, test_idx) in enumerate(tscv.split(data), 1):
            logger.info(f"Fold {fold}/{n_splits}")
            
            # Split data
            train_data = data.iloc[train_idx]
            test_data = data.iloc[test_idx]
            
            # Get date ranges
            train_start = train_data['date'].iloc[0] if 'date' in train_data.columns else None
            train_end = train_data['date'].iloc[-1] if 'date' in train_data.columns else None
            test_start = test_data['date'].iloc[0] if 'date' in test_data.columns else None
            test_end = test_data['date'].iloc[-1] if 'date' in test_data.columns else None
            
            # Prepare features
            feature_cols = [c for c in data.columns if c not in ['target', 'date', 'ticker']]
            X_train = train_data[feature_cols]
            y_train = train_data['target']
            X_test = test_data[feature_cols]
            y_test = test_data['target']
            
            # Handle missing values
            X_train = X_train.fillna(0)
            X_test = X_test.fillna(0)
            
            # Train strategy/model
            try:
                if hasattr(strategy, 'fit'):
                    strategy.fit(X_train, y_train)
                
                # Predict
                if hasattr(strategy, 'predict'):
                    y_pred = strategy.predict(X_test)
                else:
                    # Fallback: use strategy function
                    y_pred = strategy(X_test)
                
                # Calculate metrics
                from sklearn.metrics import (
                    accuracy_score, precision_score, recall_score,
                    f1_score, roc_auc_score
                )
                
                accuracy = accuracy_score(y_test, y_pred)
                precision = precision_score(y_test, y_pred, zero_division=0)
                recall = recall_score(y_test, y_pred, zero_division=0)
                f1 = f1_score(y_test, y_pred, zero_division=0)
                roc_auc = roc_auc_score(y_test, y_pred) if len(np.unique(y_test)) > 1 else 0.5
                
                # Calculate trading metrics (if possible)
                total_return, sharpe, max_dd = self._calculate_trading_metrics(
                    y_test, y_pred
                )
                
                # Create fold result
                fold_result = FoldResult(
                    fold=fold,
                    train_start=train_start,
                    train_end=train_end,
                    test_start=test_start,
                    test_end=test_end,
                    train_samples=len(train_data),
                    test_samples=len(test_data),
                    accuracy=accuracy,
                    precision=precision,
                    recall=recall,
                    f1_score=f1,
                    roc_auc=roc_auc,
                    total_return=total_return,
                    sharpe_ratio=sharpe,
                    max_drawdown=max_dd,
                )
                
                fold_results.append(fold_result)
                
                # Store in-sample metrics (use last part of training as pseudo-IS)
                if hasattr(strategy, 'predict'):
                    y_train_pred = strategy.predict(X_train.iloc[-self.min_test_size:])
                    y_train_true = y_train.iloc[-self.min_test_size:]
                    
                    is_accuracy = accuracy_score(y_train_true, y_train_pred)
                    is_metrics.append({
                        'accuracy': is_accuracy,
                        'precision': precision_score(y_train_true, y_train_pred, zero_division=0),
                        'recall': recall_score(y_train_true, y_train_pred, zero_division=0),
                        'f1': f1_score(y_train_true, y_train_pred, zero_division=0),
                        'roc_auc': roc_auc_score(y_train_true, y_train_pred) if len(np.unique(y_train_true)) > 1 else 0.5,
                        'sharpe': sharpe,
                        'return': total_return,
                    })
                
                # Store out-of-sample metrics
                oos_metrics.append({
                    'accuracy': accuracy,
                    'precision': precision,
                    'recall': recall,
                    'f1': f1,
                    'roc_auc': roc_auc,
                    'sharpe': sharpe,
                    'return': total_return,
                })
                
                logger.info(
                    f"  Fold {fold}: Accuracy={accuracy:.2%}, "
                    f"Return={total_return:.2%}, Sharpe={sharpe:.2f}"
                )
            
            except Exception as e:
                logger.error(f"Fold {fold} failed: {e}")
                continue
        
        if not fold_results:
            raise ValueError("All folds failed")
        
        # Calculate aggregate metrics
        result = self._aggregate_results(
            strategy_name=strategy_name,
            ticker=data.get('ticker', ['UNKNOWN'])[0] if isinstance(data.get('ticker'), pd.Series) else 'UNKNOWN',
            fold_results=fold_results,
            is_metrics=is_metrics,
            oos_metrics=oos_metrics,
        )
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Walk-Forward Validation Complete")
        logger.info(f"{'='*60}")
        logger.info(f"Out-of-Sample Accuracy: {result.oos_accuracy:.2%}")
        logger.info(f"Out-of-Sample Sharpe: {result.oos_sharpe:.2f}")
        logger.info(f"Stability Score: {result.stability_score:.1f}/100")
        logger.info(f"Recommendation: {result.recommendation}")
        logger.info(f"{'='*60}")
        
        return result
    
    def _calculate_trading_metrics(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
    ) -> tuple[float, float, float]:
        """Calculate trading performance metrics."""
        # Simulate trades
        positions = y_pred  # 1=long, 0=cash
        returns = y_true  # Actual returns
        
        # Strategy returns
        strategy_returns = positions * returns
        
        # Total return
        total_return = np.prod(1 + strategy_returns) - 1
        
        # Sharpe ratio (annualized)
        if len(strategy_returns) > 1 and np.std(strategy_returns) > 0:
            sharpe = np.mean(strategy_returns) / np.std(strategy_returns) * np.sqrt(252)
        else:
            sharpe = 0.0
        
        # Maximum drawdown
        cumulative = np.cumprod(1 + strategy_returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdowns = (cumulative - running_max) / running_max
        max_dd = abs(np.min(drawdowns))
        
        return total_return, sharpe, max_dd
    
    def _aggregate_results(
        self,
        strategy_name: str,
        ticker: str,
        fold_results: list[FoldResult],
        is_metrics: list[dict],
        oos_metrics: list[dict],
    ) -> WalkForwardResult:
        """Aggregate fold results into final metrics."""
        # Out-of-sample averages
        oos_accuracy = np.mean([m['accuracy'] for m in oos_metrics])
        oos_precision = np.mean([m['precision'] for m in oos_metrics])
        oos_recall = np.mean([m['recall'] for m in oos_metrics])
        oos_f1 = np.mean([m['f1'] for m in oos_metrics])
        oos_roc_auc = np.mean([m['roc_auc'] for m in oos_metrics])
        oos_sharpe = np.mean([m['sharpe'] for m in oos_metrics])
        oos_return = np.mean([m['return'] for m in oos_metrics])
        
        # In-sample averages (if available)
        if is_metrics:
            is_accuracy = np.mean([m['accuracy'] for m in is_metrics])
            is_sharpe = np.mean([m['sharpe'] for m in is_metrics])
            is_return = np.mean([m['return'] for m in is_metrics])
        else:
            is_accuracy = oos_accuracy
            is_sharpe = oos_sharpe
            is_return = oos_return
        
        # Standard deviations (stability)
        accuracy_std = np.std([m['accuracy'] for m in oos_metrics])
        return_std = np.std([m['return'] for m in oos_metrics])
        sharpe_std = np.std([m['sharpe'] for m in oos_metrics])
        
        # Performance degradation
        accuracy_degradation = is_accuracy - oos_accuracy
        sharpe_degradation = is_sharpe - oos_sharpe
        return_degradation = is_return - oos_return
        
        # Stability score (0-100)
        # Lower std = higher stability
        stability_score = 100 - (accuracy_std * 100 + return_std * 50 + sharpe_std * 20)
        stability_score = max(0, min(100, stability_score))
        
        # Determine if strategy is robust
        is_robust = (
            oos_accuracy >= 0.55 and
            oos_sharpe >= 0.5 and
            accuracy_degradation < 0.10 and
            stability_score >= 60
        )
        
        # Recommendation
        if is_robust:
            recommendation = "STRATEGY_IS_ROBUST"
        elif oos_accuracy >= 0.50 and accuracy_degradation < 0.15:
            recommendation = "NEEDS_MORE_DATA"
        elif accuracy_degradation >= 0.10:
            recommendation = "OVERFITTING_DETECTED"
        else:
            recommendation = "STRATEGY_NOT_PROFITABLE"
        
        return WalkForwardResult(
            n_splits=len(fold_results),
            strategy_name=strategy_name,
            ticker=ticker,
            is_accuracy=is_accuracy,
            is_precision=np.mean([m['precision'] for m in is_metrics]) if is_metrics else 0,
            is_recall=np.mean([m['recall'] for m in is_metrics]) if is_metrics else 0,
            is_f1=np.mean([m['f1'] for m in is_metrics]) if is_metrics else 0,
            is_roc_auc=np.mean([m['roc_auc'] for m in is_metrics]) if is_metrics else 0.5,
            is_sharpe=is_sharpe,
            is_return=is_return,
            oos_accuracy=oos_accuracy,
            oos_precision=oos_precision,
            oos_recall=oos_recall,
            oos_f1=oos_f1,
            oos_roc_auc=oos_roc_auc,
            oos_sharpe=oos_sharpe,
            oos_return=oos_return,
            accuracy_std=accuracy_std,
            return_std=return_std,
            sharpe_std=sharpe_std,
            stability_score=stability_score,
            accuracy_degradation=accuracy_degradation,
            return_degradation=return_degradation,
            sharpe_degradation=sharpe_degradation,
            fold_results=[f.to_dict() for f in fold_results],
            is_robust=is_robust,
            recommendation=recommendation,
        )


# ── Formatting Utilities ──────────────────────────────────────────────────

def format_walk_forward_summary(result: WalkForwardResult) -> str:
    """Format walk-forward results for display."""
    emoji = "✅" if result.is_robust else "⚠️"
    
    lines = [
        f"╔══════════════════════════════════════════════════════════╗",
        f"║  WALK-FORWARD VALIDATION: {result.ticker:<35s} ║",
        f"╠══════════════════════════════════════════════════════════╣",
        f"║ Strategy: {result.strategy_name:<47s} ║",
        f"║ Folds: {result.n_splits:<50d} ║",
        f"╠══════════════════════════════════════════════════════════╣",
        f"║ IN-SAMPLE PERFORMANCE".ljust(58) + "║",
        f"║   Accuracy:  {result.is_accuracy:>10.2%}  |  Sharpe: {result.is_sharpe:>10.2f}".ljust(58) + "║",
        f"║   Return:    {result.is_return:>10.2%}".ljust(58) + "║",
        f"╠══════════════════════════════════════════════════════════╣",
        f"║ OUT-OF-SAMPLE PERFORMANCE".ljust(58) + "║",
        f"║   Accuracy:  {result.oos_accuracy:>10.2%}  |  Sharpe: {result.oos_sharpe:>10.2f}".ljust(58) + "║",
        f"║   Return:    {result.oos_return:>10.2%}".ljust(58) + "║",
        f"╠══════════════════════════════════════════════════════════╣",
        f"║ STABILITY & ROBUSTNESS".ljust(58) + "║",
        f"║   Stability Score:  {result.stability_score:>10.1f}/100".ljust(58) + "║",
        f"║   Accuracy Std:     {result.accuracy_std:>10.2%}".ljust(58) + "║",
        f"║   Return Std:       {result.return_std:>10.2%}".ljust(58) + "║",
        f"║   Degradation:      {result.accuracy_degradation:>10.2%}".ljust(58) + "║",
        f"╠══════════════════════════════════════════════════════════╣",
        f"║ {emoji} {result.recommendation:<52s} ║",
        f"╚══════════════════════════════════════════════════════════╝",
    ]
    
    return "\n".join(lines)


# Singleton instance
walk_forward_validator = WalkForwardValidator()
