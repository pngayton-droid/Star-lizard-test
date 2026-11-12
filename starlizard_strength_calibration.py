"""Train-only regularised multiclass calibration for sequential team strength.

Fit softmax(log(model probabilities)/temperature + class intercepts) by
minimising Brier loss on chronological training fixtures. Never use test
outcomes or bookmaker prices to fit. Temperature and intercepts are
regularised toward identity to limit overfitting.
"""
import numpy as np
from scipy.optimize import minimize

KEYS = ["Home", "Draw", "Away"]
LABELS = {"Home win": 0, "Draw": 1, "Away win": 2}

def _softmax(z):
    z = z - np.max(z, axis=1, keepdims=True)
    exp = np.exp(z)
    return exp / exp.sum(axis=1, keepdims=True)

def transform(p, theta):
    log_p = np.log(np.clip(p, 1e-9, 1))
    temperature = np.exp(theta[0])
    offsets = np.array([theta[1], theta[2], -theta[1]-theta[2]])
    return _softmax(log_p / temperature + offsets)

def fit(frame):
    cols = [f"{key} strength" for key in KEYS]
    valid = frame[cols].notna().all(axis=1)
    subset = frame.loc[valid]
    p = subset[cols].to_numpy(dtype=float)
    y = subset["Result"].map(LABELS).to_numpy(dtype=int)
    if len(y) < 200:
        raise ValueError("Need at least 200 prior strength predictions")
    truth = np.eye(3)[y]
    def objective(theta):
        prediction = transform(p, theta)
        score = np.mean(np.sum((prediction-truth)**2, axis=1))
        penalty = .01 * float(np.sum(theta**2))
        return score + penalty
    result = minimize(objective, np.zeros(3), method="L-BFGS-B",
                      bounds=[(-.7,.7),(-.5,.5),(-.5,.5)])
    theta = result.x if result.success else np.zeros(3)
    return theta, len(y), float(objective(np.zeros(3))), float(objective(theta))
