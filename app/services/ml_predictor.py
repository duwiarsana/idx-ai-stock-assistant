"""Machine Learning prediction pipeline for stock price direction.

Trains a RandomForestClassifier on historical indicator features to predict
whether a stock's price will go UP or DOWN after 3 trading days.

Usage:
    from app.services.ml_predictor import ml_predictor

    # Train (typically called by scheduler)
    await ml_predictor.train_model(all_histories)

    # Predict
    result = ml_predictor.predict(ticker, current_features)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────
MODEL_DIR = Path("data/models")
MODEL_PATH = MODEL_DIR / "stock_predictor.joblib"
META_PATH = MODEL_DIR / "model_meta.json"
PREDICTION_HORIZON = 3   # trading days
FEATURE_COLUMNS = [
    "rsi_14",
    "macd_histogram",
    "ma_distance_pct",     # (price - sma50) / sma50 × 100
    "volume_ratio",
    "atr_pct",             # ATR / price × 100
    "price_momentum_5d",   # 5-day return %
    "bb_position",         # (price - bb_lower) / (bb_upper - bb_lower)
]


@dataclass
class MLPrediction:
    """Result of an ML prediction."""
    direction: str           # "UP" or "DOWN"
    probability: float       # 0.0 – 1.0
    model_accuracy: float    # training accuracy
    model_date: str          # when model was trained
    is_experimental: bool    # True until enough data accumulated


class MLPredictor:
    """Manages dataset creation, model training, and inference."""

    def __init__(self):
        self.model = None
        self.model_meta: dict = {}
        self._load_model()

    # ── Dataset Generation ────────────────────────────────────────────

    @staticmethod
    def build_dataset(histories: dict[str, list[dict]]) -> Optional[pd.DataFrame]:
        """Build a labelled dataset from multiple ticker histories.

        Parameters
        ----------
        histories : dict
            Mapping of ticker -> list of OHLCV dicts.

        Returns
        -------
        DataFrame with feature columns + 'label' column (1=UP, 0=DOWN)
        """
        all_rows = []

        for ticker, history in histories.items():
            if not history or len(history) < 60:
                continue

            df = pd.DataFrame(history)
            for col in ("open", "high", "low", "close", "volume"):
                df[col] = pd.to_numeric(df[col], errors="coerce")

            close = df["close"]
            high = df["high"]
            low = df["low"]
            volume = df["volume"]

            # ── Compute features over the entire series ──

            # RSI-14
            delta = close.diff()
            gain = delta.where(delta > 0, 0.0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
            rs = gain / loss
            df["rsi_14"] = 100 - (100 / (1 + rs))

            # MACD histogram
            ema12 = close.ewm(span=12, adjust=False).mean()
            ema26 = close.ewm(span=26, adjust=False).mean()
            macd_line = ema12 - ema26
            signal_line = macd_line.ewm(span=9, adjust=False).mean()
            df["macd_histogram"] = macd_line - signal_line

            # MA distance
            sma50 = close.rolling(50).mean()
            df["ma_distance_pct"] = ((close - sma50) / sma50 * 100).where(sma50 > 0, 0)

            # Volume ratio
            avg_vol = volume.rolling(20).mean()
            df["volume_ratio"] = (volume / avg_vol).where(avg_vol > 0, 1.0)

            # ATR %
            prev_close = close.shift(1)
            tr = pd.concat([
                high - low,
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ], axis=1).max(axis=1)
            atr = tr.rolling(14).mean()
            df["atr_pct"] = (atr / close * 100).where(close > 0, 0)

            # Price momentum 5d
            df["price_momentum_5d"] = close.pct_change(5) * 100

            # Bollinger position
            bb_mid = close.rolling(20).mean()
            bb_std = close.rolling(20).std()
            bb_upper = bb_mid + 2 * bb_std
            bb_lower = bb_mid - 2 * bb_std
            bb_range = bb_upper - bb_lower
            df["bb_position"] = ((close - bb_lower) / bb_range).where(bb_range > 0, 0.5)

            # ── Label: price direction after PREDICTION_HORIZON days ──
            future_close = close.shift(-PREDICTION_HORIZON)
            df["label"] = (future_close > close).astype(int)

            # Drop NaN rows
            feature_df = df[FEATURE_COLUMNS + ["label"]].dropna()
            if len(feature_df) > 0:
                feature_df = feature_df.copy()
                feature_df["ticker"] = ticker
                all_rows.append(feature_df)

        if not all_rows:
            return None

        dataset = pd.concat(all_rows, ignore_index=True)
        logger.info(f"ML dataset built: {len(dataset)} samples from {len(histories)} tickers")
        return dataset

    # ── Training ──────────────────────────────────────────────────────

    def train(self, histories: dict[str, list[dict]]) -> dict:
        """Train a RandomForestClassifier on the built dataset.

        Returns
        -------
        dict with training metrics.
        """
        try:
            from sklearn.ensemble import RandomForestClassifier
            from sklearn.model_selection import cross_val_score
            import joblib
        except ImportError:
            logger.error("scikit-learn not installed — cannot train ML model")
            return {"error": "scikit-learn not installed"}

        dataset = self.build_dataset(histories)
        if dataset is None or len(dataset) < 100:
            msg = f"Insufficient data for training: {len(dataset) if dataset is not None else 0} samples"
            logger.warning(msg)
            return {"error": msg}

        X = dataset[FEATURE_COLUMNS].values
        y = dataset["label"].values

        # Train
        model = RandomForestClassifier(
            n_estimators=200,
            max_depth=10,
            min_samples_split=5,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=-1,
        )
        model.fit(X, y)

        # Cross-validation accuracy
        cv_scores = cross_val_score(model, X, y, cv=5, scoring="accuracy")
        accuracy = float(cv_scores.mean())

        # Feature importance
        importances = dict(zip(FEATURE_COLUMNS, [round(float(x), 4) for x in model.feature_importances_]))

        # Save model
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, MODEL_PATH)

        self.model = model
        self.model_meta = {
            "trained_at": datetime.now().isoformat(),
            "samples": len(dataset),
            "accuracy": round(accuracy, 4),
            "cv_scores": [round(float(s), 4) for s in cv_scores],
            "feature_importance": importances,
            "is_experimental": len(dataset) < 5000,
        }

        with open(META_PATH, "w") as f:
            json.dump(self.model_meta, f, indent=2)

        logger.info(
            f"ML model trained: accuracy={accuracy:.2%}, "
            f"samples={len(dataset)}, experimental={self.model_meta['is_experimental']}"
        )
        return self.model_meta

    # ── Prediction ────────────────────────────────────────────────────

    def predict(self, ticker: str, features: dict) -> Optional[MLPrediction]:
        """Predict price direction for a stock given current features.

        Parameters
        ----------
        ticker : str
        features : dict
            Must contain keys matching FEATURE_COLUMNS.
        """
        if self.model is None:
            logger.debug("No ML model loaded — skipping prediction")
            return None

        try:
            # Build feature vector
            feature_vector = []
            for col in FEATURE_COLUMNS:
                val = features.get(col)
                if val is None or (isinstance(val, float) and np.isnan(val)):
                    val = 0.0
                feature_vector.append(float(val))

            X = np.array([feature_vector])
            proba = self.model.predict_proba(X)[0]

            # Class 1 = UP
            up_prob = float(proba[1]) if len(proba) > 1 else 0.5
            direction = "UP" if up_prob >= 0.5 else "DOWN"
            probability = up_prob if direction == "UP" else (1 - up_prob)

            return MLPrediction(
                direction=direction,
                probability=round(probability, 4),
                model_accuracy=self.model_meta.get("accuracy", 0),
                model_date=self.model_meta.get("trained_at", "unknown"),
                is_experimental=self.model_meta.get("is_experimental", True),
            )

        except Exception as e:
            logger.warning(f"ML prediction error for {ticker}: {e}")
            return None

    def extract_features(self, technicals: dict) -> dict:
        """Extract ML feature dict from technicals dict."""
        close = technicals.get("current_price", 0)
        sma50 = technicals.get("sma_50")
        bb_upper = technicals.get("bb_upper")
        bb_lower = technicals.get("bb_lower")

        ma_dist = ((close - sma50) / sma50 * 100) if sma50 and sma50 > 0 else 0
        if bb_upper and bb_lower and (bb_upper - bb_lower) > 0:
            bb_pos = (close - bb_lower) / (bb_upper - bb_lower)
        else:
            bb_pos = 0.5

        return {
            "rsi_14": technicals.get("rsi_14", 50),
            "macd_histogram": technicals.get("macd_histogram", 0),
            "ma_distance_pct": ma_dist,
            "volume_ratio": technicals.get("volume_ratio", 1.0),
            "atr_pct": technicals.get("atr_pct", 0),
            "price_momentum_5d": technicals.get("change_5d_pct", 0),
            "bb_position": bb_pos,
        }

    # ── Persistence ───────────────────────────────────────────────────

    def _load_model(self):
        """Load saved model from disk if available."""
        if not MODEL_PATH.exists():
            logger.info("No saved ML model found — predictions disabled until training")
            return

        try:
            import joblib
            self.model = joblib.load(MODEL_PATH)

            if META_PATH.exists():
                with open(META_PATH) as f:
                    self.model_meta = json.load(f)

            logger.info(
                f"ML model loaded: accuracy={self.model_meta.get('accuracy', 'N/A')}, "
                f"trained={self.model_meta.get('trained_at', 'unknown')}"
            )
        except Exception as e:
            logger.warning(f"Failed to load ML model: {e}")
            self.model = None


# Singleton
ml_predictor = MLPredictor()
