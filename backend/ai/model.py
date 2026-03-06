"""
AI LEARNING MODEL
Trains on past XAUUSD trade outcomes to improve signals.
Uses Random Forest — no GPU needed, works on free cloud.
"""

import os
import json
import logging
import numpy as np
import pandas as pd
from datetime import datetime

log = logging.getLogger("AIModel")

MODEL_PATH   = "ai/model.pkl"
HISTORY_PATH = "ai/trade_history.json"


class GoldAIModel:
    """
    A self-improving AI model for XAUUSD trading.
    Phase 1: Rule-based with confidence scoring.
    Phase 2: Machine learning (activates after 50 trades).
    """

    def __init__(self):
        self.model        = None
        self.scaler       = None
        self.is_trained   = False
        self.trade_history = self._load_history()
        self._try_load_model()

    # ─────────────────────────────────────────
    #  PREDICT — called on every signal
    # ─────────────────────────────────────────
    def predict(self, features: dict) -> float:
        """
        Returns confidence score 0.0 – 1.0
        Uses ML model if trained, else rule-based scoring.
        """
        if self.is_trained and self.model:
            return self._ml_predict(features)
        return self._rule_predict(features)

    # ─────────────────────────────────────────
    #  LEARN — called after each trade closes
    # ─────────────────────────────────────────
    def record_outcome(self, features: dict, pnl: float):
        """
        Store trade result for future training.
        Retrain model every 50 trades.
        """
        outcome = 1 if pnl > 0 else 0
        record  = {**features, "outcome": outcome, "pnl": pnl, "time": str(datetime.now())}
        self.trade_history.append(record)
        self._save_history()

        from config.settings import RETRAIN_EVERY
        if len(self.trade_history) % RETRAIN_EVERY == 0:
            log.info(f"Retraining on {len(self.trade_history)} trades...")
            self.train()

    # ─────────────────────────────────────────
    #  TRAIN
    # ─────────────────────────────────────────
    def train(self):
        """
        Train Random Forest on historical trade data.
        Minimum 20 trades required.
        """
        if len(self.trade_history) < 20:
            log.info("Not enough trades to train (need 20+)")
            return False

        try:
            from sklearn.ensemble import RandomForestClassifier
            from sklearn.preprocessing import StandardScaler
            from sklearn.model_selection import train_test_split
            import pickle

            df = pd.DataFrame(self.trade_history)
            feature_cols = [c for c in df.columns if c not in ["outcome", "pnl", "time"]]
            df = df.dropna(subset=feature_cols + ["outcome"])

            X = df[feature_cols].values
            y = df["outcome"].values

            scaler = StandardScaler()
            X_sc   = scaler.fit_transform(X)

            X_train, X_test, y_train, y_test = train_test_split(X_sc, y, test_size=0.2, random_state=42)

            model = RandomForestClassifier(
                n_estimators=100,
                max_depth=6,
                min_samples_leaf=3,
                random_state=42,
            )
            model.fit(X_train, y_train)

            acc = model.score(X_test, y_test)
            log.info(f"Model trained ✓ accuracy={acc:.1%} on {len(y)} trades")

            os.makedirs("ai", exist_ok=True)
            with open(MODEL_PATH, "wb") as f:
                pickle.dump({"model": model, "scaler": scaler, "features": feature_cols}, f)

            self.model      = model
            self.scaler     = scaler
            self.feat_cols  = feature_cols
            self.is_trained = True
            return True

        except ImportError:
            log.warning("scikit-learn not installed — using rule-based mode")
            return False

    # ─────────────────────────────────────────
    #  PREDICTION METHODS
    # ─────────────────────────────────────────
    def _ml_predict(self, features: dict) -> float:
        try:
            vals = [features.get(c, 0) for c in self.feat_cols]
            X    = np.array(vals).reshape(1, -1)
            X_sc = self.scaler.transform(X)
            prob = self.model.predict_proba(X_sc)[0][1]
            return float(prob)
        except Exception as e:
            log.error(f"ML predict error: {e}")
            return self._rule_predict(features)

    def _rule_predict(self, features: dict) -> float:
        """
        Rule-based confidence scoring.
        Used when ML model is not yet trained.
        """
        score = 0.50  # baseline

        trend    = features.get("trend", 0)
        rsi      = features.get("rsi", 50)
        sweep    = features.get("has_sweep", 0)
        session  = features.get("in_session", 0)
        rejection = features.get("rejection", 0)

        if trend != 0:
            score += 0.08

        if sweep:
            score += 0.15

        if session:
            score += 0.08

        if rejection:
            score += 0.07

        # RSI alignment
        if rsi < 40 and trend == 1:
            score += 0.08
        elif rsi > 60 and trend == -1:
            score += 0.08

        return min(score, 0.95)

    # ─────────────────────────────────────────
    #  HISTORY PERSISTENCE
    # ─────────────────────────────────────────
    def _load_history(self) -> list:
        if os.path.exists(HISTORY_PATH):
            try:
                with open(HISTORY_PATH) as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_history(self):
        os.makedirs("ai", exist_ok=True)
        with open(HISTORY_PATH, "w") as f:
            json.dump(self.trade_history[-5000:], f)  # keep last 5000

    def _try_load_model(self):
        if not os.path.exists(MODEL_PATH):
            return
        try:
            import pickle
            with open(MODEL_PATH, "rb") as f:
                data = pickle.load(f)
            self.model      = data["model"]
            self.scaler     = data["scaler"]
            self.feat_cols  = data["features"]
            self.is_trained = True
            log.info(f"Model loaded ✓ ({len(self.trade_history)} training records)")
        except Exception as e:
            log.warning(f"Could not load model: {e}")

    def get_stats(self) -> dict:
        if not self.trade_history:
            return {"status": "no_data"}
        wins   = sum(1 for t in self.trade_history if t.get("outcome") == 1)
        total  = len(self.trade_history)
        return {
            "total_samples": total,
            "win_rate":      round(wins / total, 4) if total > 0 else 0,
            "model_active":  self.is_trained,
        }
