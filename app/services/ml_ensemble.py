"""ML Ensemble - Advanced Machine Learning for Stock Prediction.

Combines multiple ML models (XGBoost, LightGBm, RandomForest, etc.) with 
stacking ensemble for improved prediction accuracy.

Features:
- Multiple ML models (XGBoost, LightGBM, RandomForest, LogisticRegression)
- Stacking ensemble with meta-learner
- Feature importance analysis
- SHAP values for interpretability
- Model persistence
- Auto-retraining

Usage:
    from app.services.ml_ensemble import MLEnsemble
    
    ensemble = MLEnsemble()
    
    # Train
    ensemble.train(X_train, y_train)
    
    # Predict
    prediction = ensemble.predict(X_test)
    proba = ensemble.predict_proba(X_test)
    
    # Get feature importance
    importance = ensemble.get_feature_importance()
"""

from __future__ import annotations

import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Union
from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd
from sklearn.ensemble import (
    RandomForestClassifier,
    GradientBoostingClassifier,
    VotingClassifier,
    StackingClassifier,
)
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
import joblib

logger = logging.getLogger(__name__)

# Try to import optional dependencies
try:
    import xgboost as xgb
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False
    logger.warning("XGBoost not installed - install with: pip install xgboost")

try:
    import lightgbm as lgb
    HAS_LIGHTGBM = True
except ImportError:
    HAS_LIGHTGBM = False
    logger.warning("LightGBM not installed - install with: pip install lightgbm")

try:
    import shap
    HAS_SHAP = True
except ImportError:
    HAS_SHAP = False
    logger.warning("SHAP not installed - install with: pip install shap")


# ── Data Classes ───────────────────────────────────────────────────────────

@dataclass
class ModelMetrics:
    """Model performance metrics."""
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    roc_auc: float
    training_samples: int
    training_time: float
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MLPrediction:
    """ML prediction result."""
    ticker: str
    prediction: int  # 0=DOWN, 1=UP
    probability: float  # 0.0 - 1.0
    confidence: str  # LOW, MEDIUM, HIGH
    models_agreement: float  # 0.0 - 1.0
    feature_importance: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return asdict(self)


# ── ML Ensemble ───────────────────────────────────────────────────────────

class MLEnsemble:
    """Ensemble of multiple ML models for stock prediction."""
    
    MODEL_DIR = Path("data/models")
    FEATURE_COLUMNS = [
        'rsi_14', 'macd_histogram', 'ma_distance_pct', 'volume_ratio',
        'atr_pct', 'price_momentum_5d', 'bb_position', 'adx',
        'stoch_k', 'willr_14', 'cci_20', 'roc_10',
        'obv_change', 'mfi_14', 'cmf_20',
        'revenue_growth_yoy', 'earnings_growth_yoy', 'roe', 'roa',
        'debt_to_equity', 'current_ratio', 'pe_ratio', 'pb_ratio',
    ]
    
    def __init__(self, use_stacking: bool = True):
        self.use_stacking = use_stacking
        self.models = {}
        self.ensemble = None
        self.scaler = StandardScaler()
        self.is_fitted = False
        self.metrics: Optional[ModelMetrics] = None
        self.feature_importance: dict = {}
        
        # Create model directory
        self.MODEL_DIR.mkdir(parents=True, exist_ok=True)
        
        # Initialize models
        self._initialize_models()
    
    def _initialize_models(self):
        """Initialize individual ML models."""
        
        # XGBoost
        if HAS_XGBOOST:
            self.models['xgboost'] = xgb.XGBClassifier(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.01,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                n_jobs=-1,
                use_label_encoder=False,
                eval_metric='logloss',
            )
            logger.info("XGBoost model initialized")
        
        # LightGBM
        if HAS_LIGHTGBM:
            self.models['lightgbm'] = lgb.LGBMClassifier(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.01,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                n_jobs=-1,
                verbose=-1,
            )
            logger.info("LightGBM model initialized")
        
        # Random Forest
        self.models['random_forest'] = RandomForestClassifier(
            n_estimators=200,
            max_depth=10,
            min_samples_split=5,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=-1,
        )
        logger.info("Random Forest model initialized")
        
        # Gradient Boosting
        self.models['gradient_boosting'] = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.01,
            random_state=42,
        )
        logger.info("Gradient Boosting model initialized")
        
        # Logistic Regression (for ensemble diversity)
        self.models['logistic_regression'] = LogisticRegression(
            C=0.1,
            penalty='l2',
            random_state=42,
            max_iter=1000,
            n_jobs=-1,
        )
        logger.info("Logistic Regression model initialized")
        
        # MLP Neural Network
        self.models['mlp'] = MLPClassifier(
            hidden_layer_sizes=(128, 64, 32),
            activation='relu',
            solver='adam',
            alpha=0.001,
            batch_size=32,
            learning_rate='adaptive',
            max_iter=200,
            random_state=42,
            early_stopping=True,
            validation_fraction=0.1,
        )
        logger.info("MLP Neural Network model initialized")
        
        logger.info(f"Initialized {len(self.models)} ML models")
    
    def train(
        self,
        X: Union[pd.DataFrame, np.ndarray],
        y: Union[pd.Series, np.ndarray],
        X_test: Optional[Union[pd.DataFrame, np.ndarray]] = None,
        y_test: Optional[Union[pd.Series, np.ndarray]] = None,
    ) -> ModelMetrics:
        """Train the ensemble on historical data.
        
        Parameters
        ----------
        X : pd.DataFrame or np.ndarray
            Training features
        y : pd.Series or np.ndarray
            Training labels (0=DOWN, 1=UP)
        X_test : optional
            Test features for validation
        y_test : optional
            Test labels for validation
        
        Returns
        -------
        ModelMetrics
            Training/validation metrics
        """
        import time
        start_time = time.time()
        
        # Convert to numpy if DataFrame
        if isinstance(X, pd.DataFrame):
            X = X[self.FEATURE_COLUMNS].values
        if isinstance(y, pd.Series):
            y = y.values
        
        # Handle missing values
        X = np.nan_to_num(X, nan=0.0)
        
        # Scale features
        X_scaled = self.scaler.fit_transform(X)
        
        # Train individual models
        logger.info(f"Training {len(self.models)} models on {len(X)} samples...")
        
        for name, model in self.models.items():
            try:
                logger.info(f"  Training {name}...")
                model.fit(X_scaled, y)
                logger.info(f"  ✓ {name} trained successfully")
            except Exception as e:
                logger.error(f"  ✗ {name} training failed: {e}")
                del self.models[name]
        
        # Create stacking ensemble if enabled and enough models
        if self.use_stacking and len(self.models) >= 3:
            logger.info("Creating stacking ensemble...")
            
            # Prepare base models for stacking
            base_models = list(self.models.items())
            
            # Stacking with logistic regression as meta-learner
            self.ensemble = StackingClassifier(
                estimators=base_models,
                final_estimator=LogisticRegression(C=1.0, max_iter=1000),
                cv=5,
                n_jobs=-1,
            )
            
            try:
                self.ensemble.fit(X_scaled, y)
                logger.info("✓ Stacking ensemble trained successfully")
            except Exception as e:
                logger.warning(f"Stacking ensemble failed: {e}, using voting instead")
                self.ensemble = None
        
        # If stacking failed, use voting ensemble
        if self.ensemble is None and len(self.models) >= 2:
            logger.info("Creating voting ensemble...")
            self.ensemble = VotingClassifier(
                estimators=list(self.models.items()),
                voting='soft',
                n_jobs=-1,
            )
            self.ensemble.fit(X_scaled, y)
            logger.info("✓ Voting ensemble trained successfully")
        
        # Calculate metrics
        training_time = time.time() - start_time
        
        # Predict on training set
        y_pred = self.predict(X, return_raw=True)
        
        metrics = ModelMetrics(
            accuracy=accuracy_score(y, y_pred),
            precision=precision_score(y, y_pred, zero_division=0),
            recall=recall_score(y, y_pred, zero_division=0),
            f1_score=f1_score(y, y_pred, zero_division=0),
            roc_auc=roc_auc_score(y, y_pred) if len(np.unique(y)) > 1 else 0.5,
            training_samples=len(X),
            training_time=training_time,
        )
        
        # Validate on test set if provided
        if X_test is not None and y_test is not None:
            if isinstance(X_test, pd.DataFrame):
                X_test = X_test[self.FEATURE_COLUMNS].values
            if isinstance(y_test, pd.Series):
                y_test = y_test.values
            
            X_test = np.nan_to_num(X_test, nan=0.0)
            X_test_scaled = self.scaler.transform(X_test)
            
            y_test_pred = self.predict(X_test, return_raw=True)
            
            logger.info(f"\n📊 Test Set Metrics:")
            logger.info(f"  Accuracy:  {accuracy_score(y_test, y_test_pred):.2%}")
            logger.info(f"  Precision: {precision_score(y_test, y_test_pred, zero_division=0):.2%}")
            logger.info(f"  Recall:    {recall_score(y_test, y_test_pred, zero_division=0):.2%}")
            logger.info(f"  F1 Score:  {f1_score(y_test, y_test_pred, zero_division=0):.2%}")
        
        self.metrics = metrics
        self.is_fitted = True
        
        # Calculate feature importance
        self._calculate_feature_importance(X_scaled, y)
        
        # Save models
        self.save()
        
        logger.info(f"\n✅ Training complete in {training_time:.1f}s")
        logger.info(f"  Accuracy: {metrics.accuracy:.2%}")
        logger.info(f"  F1 Score: {metrics.f1_score:.2%}")
        logger.info(f"  ROC AUC: {metrics.roc_auc:.2f}")
        
        return metrics
    
    def predict(
        self,
        X: Union[pd.DataFrame, np.ndarray],
        return_raw: bool = False,
    ) -> Union[np.ndarray, list[MLPrediction]]:
        """Predict stock price direction.
        
        Parameters
        ----------
        X : pd.DataFrame or np.ndarray
            Features to predict on
        return_raw : bool, default=False
            If True, return raw predictions (0/1)
            If False, return MLPrediction objects
        
        Returns
        -------
        np.ndarray or list[MLPrediction]
            Predictions
        """
        if not self.is_fitted:
            raise ValueError("Model not fitted. Call train() first.")
        
        # Convert to numpy if DataFrame
        if isinstance(X, pd.DataFrame):
            tickers = X.get('ticker', ['UNKNOWN'] * len(X)).tolist()
            X = X[self.FEATURE_COLUMNS].values
        else:
            tickers = ['UNKNOWN'] * len(X)
        
        # Handle missing values
        X = np.nan_to_num(X, nan=0.0)
        
        # Scale features
        X_scaled = self.scaler.transform(X)
        
        # Predict using ensemble or best model
        if self.ensemble is not None:
            y_pred = self.ensemble.predict(X_scaled)
            y_proba = self.ensemble.predict_proba(X_scaled)[:, 1]
        else:
            # Use best individual model
            best_model = list(self.models.values())[0]
            y_pred = best_model.predict(X_scaled)
            y_proba = best_model.predict_proba(X_scaled)[:, 1]
        
        if return_raw:
            return y_pred
        
        # Create prediction objects
        predictions = []
        for i in range(len(X)):
            ticker = tickers[i] if i < len(tickers) else 'UNKNOWN'
            pred = int(y_pred[i])
            proba = float(y_proba[i])
            
            # Determine confidence
            if proba >= 0.7:
                confidence = 'HIGH'
            elif proba >= 0.55:
                confidence = 'MEDIUM'
            else:
                confidence = 'LOW'
            
            # Calculate models agreement
            if len(self.models) > 1:
                model_preds = []
                for model in self.models.values():
                    model_pred = model.predict(X_scaled[i:i+1])[0]
                    model_preds.append(model_pred)
                agreement = sum(model_preds) / len(model_preds)
                agreement = max(agreement, 1 - agreement)  # Agreement ratio
            else:
                agreement = 1.0
            
            predictions.append(MLPrediction(
                ticker=ticker,
                prediction=pred,
                probability=proba,
                confidence=confidence,
                models_agreement=agreement,
                feature_importance=self.feature_importance,
            ))
        
        return predictions
    
    def predict_single(self, features: dict) -> MLPrediction:
        """Predict for a single stock.
        
        Parameters
        ----------
        features : dict
            Feature dictionary with keys matching FEATURE_COLUMNS
        
        Returns
        -------
        MLPrediction
            Prediction result
        """
        # Convert to DataFrame
        df = pd.DataFrame([features])
        predictions = self.predict(df)
        return predictions[0]
    
    def _calculate_feature_importance(self, X: np.ndarray, y: np.ndarray):
        """Calculate feature importance using permutation importance."""
        try:
            # Use the best model for feature importance
            if self.ensemble is not None:
                model = self.ensemble
            else:
                model = list(self.models.values())[0]
            
            # Get feature importance from model
            if hasattr(model, 'feature_importances_'):
                importances = model.feature_importances_
            else:
                # Fallback: use permutation importance
                from sklearn.inspection import permutation_importance
                result = permutation_importance(model, X, y, n_repeats=10, random_state=42, n_jobs=-1)
                importances = result.importances_mean
            
            # Store feature importance
            self.feature_importance = dict(zip(
                self.FEATURE_COLUMNS,
                [round(float(imp), 4) for imp in importances]
            ))
            
            # Sort by importance
            self.feature_importance = dict(sorted(
                self.feature_importance.items(),
                key=lambda x: x[1],
                reverse=True,
            )[:20])  # Top 20 features
            
            logger.info(f"Feature importance calculated: {len(self.feature_importance)} features")
        
        except Exception as e:
            logger.warning(f"Feature importance calculation failed: {e}")
            self.feature_importance = {}
    
    def get_shap_values(self, X: Union[pd.DataFrame, np.ndarray]) -> dict:
        """Get SHAP values for model interpretability.
        
        Parameters
        ----------
        X : pd.DataFrame or np.ndarray
            Features to explain
        
        Returns
        -------
        dict
            SHAP values and summary
        """
        if not HAS_SHAP:
            logger.warning("SHAP not installed - cannot calculate SHAP values")
            return {}
        
        if not self.is_fitted:
            raise ValueError("Model not fitted. Call train() first.")
        
        try:
            # Convert to numpy if DataFrame
            if isinstance(X, pd.DataFrame):
                X = X[self.FEATURE_COLUMNS].values
            
            X = np.nan_to_num(X, nan=0.0)
            X_scaled = self.scaler.transform(X)
            
            # Use a subset for faster computation
            X_sample = X_scaled[:100] if len(X_scaled) > 100 else X_scaled
            
            # Create explainer
            if self.ensemble is not None:
                explainer = shap.TreeExplainer(self.ensemble)
            else:
                explainer = shap.KernelExplainer(list(self.models.values())[0].predict_proba, X_sample)
            
            # Calculate SHAP values
            shap_values = explainer.shap_values(X_sample)
            
            # Get summary
            summary = {
                'mean_abs_shap_values': {},
                'feature_importance_ranking': [],
            }
            
            # Calculate mean absolute SHAP values
            if isinstance(shap_values, list):
                # Multi-class
                shap_mean = np.abs(shap_values[0]).mean(axis=0)
            else:
                shap_mean = np.abs(shap_values).mean(axis=0)
            
            for i, col in enumerate(self.FEATURE_COLUMNS):
                if i < len(shap_mean):
                    summary['mean_abs_shap_values'][col] = float(shap_mean[i])
            
            # Rank features
            sorted_features = sorted(
                summary['mean_abs_shap_values'].items(),
                key=lambda x: x[1],
                reverse=True,
            )
            summary['feature_importance_ranking'] = [f[0] for f in sorted_features[:10]]
            
            return summary
        
        except Exception as e:
            logger.warning(f"SHAP calculation failed: {e}")
            return {}
    
    def save(self, filepath: Optional[str] = None):
        """Save trained models to disk."""
        if filepath is None:
            filepath = self.MODEL_DIR / "ml_ensemble.joblib"
        
        try:
            joblib.dump({
                'models': self.models,
                'ensemble': self.ensemble,
                'scaler': self.scaler,
                'feature_importance': self.feature_importance,
                'metrics': self.metrics.to_dict() if self.metrics else None,
                'feature_columns': self.FEATURE_COLUMNS,
            }, filepath)
            
            logger.info(f"Models saved to {filepath}")
        
        except Exception as e:
            logger.error(f"Failed to save models: {e}")
    
    def load(self, filepath: Optional[str] = None) -> bool:
        """Load trained models from disk."""
        if filepath is None:
            filepath = self.MODEL_DIR / "ml_ensemble.joblib"
        
        if not Path(filepath).exists():
            logger.info(f"No saved models found at {filepath}")
            return False
        
        try:
            data = joblib.load(filepath)
            
            self.models = data.get('models', {})
            self.ensemble = data.get('ensemble', None)
            self.scaler = data.get('scaler', StandardScaler())
            self.feature_importance = data.get('feature_importance', {})
            self.feature_columns = data.get('feature_columns', self.FEATURE_COLUMNS)
            
            metrics_data = data.get('metrics', None)
            if metrics_data:
                self.metrics = ModelMetrics(**metrics_data)
            
            self.is_fitted = len(self.models) > 0
            
            logger.info(f"Models loaded from {filepath}")
            logger.info(f"  Models: {list(self.models.keys())}")
            if self.metrics:
                logger.info(f"  Accuracy: {self.metrics.accuracy:.2%}")
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to load models: {e}")
            return False
    
    def get_models(self) -> list[str]:
        """Get list of available models."""
        return list(self.models.keys())
    
    def get_status(self) -> dict:
        """Get ensemble status."""
        return {
            'is_fitted': self.is_fitted,
            'models': list(self.models.keys()),
            'ensemble_type': 'stacking' if self.ensemble and isinstance(self.ensemble, StackingClassifier) else 'voting' if self.ensemble else 'none',
            'metrics': self.metrics.to_dict() if self.metrics else None,
            'feature_importance': self.feature_importance,
        }


# Singleton instance
ml_ensemble = MLEnsemble()
