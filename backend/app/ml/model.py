"""Regresión logística en numpy + validación walk-forward.

Suficiente para un filtro de señales, sin arrastrar scikit-learn.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .features import FEATURE_NAMES, build_dataset

MODEL_PATH = Path(__file__).resolve().parent.parent.parent / "models" / "btc_model.json"


def _sigmoid(z: np.ndarray) -> np.ndarray:
    z = np.clip(z, -40, 40)
    return 1.0 / (1.0 + np.exp(-z))


def _standardize(X: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    std = np.where(std == 0, 1.0, std)
    return (X - mean) / std


def fit_logreg(
    X: np.ndarray,
    y: np.ndarray,
    lr: float = 0.08,
    epochs: int = 600,
    l2: float = 1e-3,
) -> tuple[np.ndarray, float, np.ndarray, np.ndarray]:
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    Xs = _standardize(X, mean, std)

    n, k = Xs.shape
    weights = np.zeros(k)
    bias = 0.0

    for _ in range(epochs):
        z = Xs @ weights + bias
        pred = _sigmoid(z)
        error = pred - y
        grad_w = (Xs.T @ error) / n + l2 * weights
        grad_b = float(error.mean())
        weights -= lr * grad_w
        bias -= lr * grad_b

    return weights, bias, mean, std


def predict_proba(model: dict[str, Any], features: np.ndarray) -> float:
    weights = np.asarray(model["weights"], dtype=float)
    mean = np.asarray(model["mean"], dtype=float)
    std = np.asarray(model["std"], dtype=float)
    x = (np.asarray(features, dtype=float) - mean) / np.where(std == 0, 1.0, std)
    return float(_sigmoid(np.array([x @ weights + float(model["bias"])]))[0])


def _evaluate(model: dict, X: np.ndarray, y: np.ndarray) -> dict:
    probs = np.array([predict_proba(model, row) for row in X]) if len(X) < 5000 else _vector_predict(model, X)
    preds = (probs >= 0.5).astype(int)
    acc = float((preds == y).mean()) if len(y) else 0.0
    tp = int(((preds == 1) & (y == 1)).sum())
    fp = int(((preds == 1) & (y == 0)).sum())
    fn = int(((preds == 0) & (y == 1)).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "accuracy": round(acc, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "samples": int(len(y)),
    }


def _vector_predict(model: dict, X: np.ndarray) -> np.ndarray:
    weights = np.asarray(model["weights"], dtype=float)
    mean = np.asarray(model["mean"], dtype=float)
    std = np.asarray(model["std"], dtype=float)
    Xs = (X - mean) / np.where(std == 0, 1.0, std)
    return _sigmoid(Xs @ weights + float(model["bias"]))


def train_and_save(
    df_raw: pd.DataFrame,
    params: dict,
    horizon: int = 3,
    folds: int = 4,
    path: Path | None = None,
) -> dict[str, Any]:
    X, y, times = build_dataset(df_raw, params, horizon=horizon)
    if len(X) < 200:
        raise ValueError(f"muy pocos datos para entrenar ({len(X)} muestras)")

    # Walk-forward: cada fold entrena con el pasado y valida con el futuro.
    fold_size = len(X) // (folds + 1)
    fold_metrics = []
    for i in range(1, folds + 1):
        train_end = fold_size * i
        test_end = min(len(X), fold_size * (i + 1))
        if test_end - train_end < 30:
            continue
        weights, bias, mean, std = fit_logreg(X[:train_end], y[:train_end])
        model = {"weights": weights.tolist(), "bias": bias, "mean": mean.tolist(), "std": std.tolist()}
        metrics = _evaluate(model, X[train_end:test_end], y[train_end:test_end])
        metrics["fold"] = i
        metrics["train_samples"] = int(train_end)
        fold_metrics.append(metrics)

    # Modelo final: todos los datos.
    weights, bias, mean, std = fit_logreg(X, y)
    model = {
        "feature_names": FEATURE_NAMES,
        "weights": weights.tolist(),
        "bias": float(bias),
        "mean": mean.tolist(),
        "std": std.tolist(),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "horizon": horizon,
        "samples": int(len(X)),
        "base_rate": float(y.mean()),
    }

    avg_acc = float(np.mean([m["accuracy"] for m in fold_metrics])) if fold_metrics else 0.0
    model["metrics"] = {
        "walk_forward_accuracy": round(avg_acc, 4),
        "folds": fold_metrics,
        "base_rate": round(float(y.mean()), 4),
        "samples": int(len(X)),
        "from": str(times.iloc[0]) if len(times) else None,
        "to": str(times.iloc[-1]) if len(times) else None,
    }

    target = path or MODEL_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(model, indent=2), encoding="utf-8")
    return model["metrics"]


def load_model(path: Path | None = None) -> dict[str, Any] | None:
    target = path or MODEL_PATH
    if not target.exists():
        return None
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def model_status() -> dict[str, Any]:
    model = load_model()
    if not model:
        return {"trained": False}
    return {
        "trained": True,
        "trained_at": model.get("trained_at"),
        "metrics": model.get("metrics", {}),
        "features": model.get("feature_names", []),
        "samples": model.get("samples"),
    }
