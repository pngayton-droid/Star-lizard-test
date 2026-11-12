"""Train-only multiclass probability calibration and diagnostics."""
import numpy as np
import pandas as pd

OUTCOMES = ("Home win", "Draw", "Away win")
KEYS = ("Home", "Draw", "Away")

def matrix(frame, suffix):
    return frame[[f"{key} {suffix}" for key in KEYS]].to_numpy(dtype=float)

def targets(frame):
    return frame["Result"].map({label: i for i, label in enumerate(OUTCOMES)}).to_numpy(dtype=int)

def brier(p, y):
    return float(np.mean(np.sum((p - np.eye(3)[y]) ** 2, axis=1)))

def fit_calibration(train, suffix="adjusted"):
    """Choose one global shrinkage strength using TRAIN dates only.

    p_cal = (1-alpha)*p_model + alpha*train_outcome_frequencies.
    Small search deliberately avoids tuning against held-out matches.
    """
    p = matrix(train, suffix)
    y = targets(train)
    mask = np.isfinite(p).all(axis=1) & np.isfinite(y)
    p, y = p[mask], y[mask]
    if len(y) < 100:
        raise ValueError("Need at least 100 training matches")
    prior = np.bincount(y, minlength=3).astype(float) / len(y)
    choices = np.arange(0, 1.001, .05)
    scores = [brier((1-a)*p + a*prior, y) for a in choices]
    alpha = float(choices[int(np.argmin(scores))])
    return {"alpha": alpha, "prior": prior, "train_size": len(y),
            "train_raw_brier": brier(p, y), "train_cal_brier": min(scores)}

def apply_calibration(frame, fit, suffix="adjusted"):
    p = matrix(frame, suffix)
    return (1-fit["alpha"])*p + fit["alpha"]*fit["prior"]

def reliability(frame, p, bins=5):
    y = targets(frame)
    rows = []
    for j, name in enumerate(OUTCOMES):
        for lo in np.linspace(0, 1, bins, endpoint=False):
            hi = lo + 1 / bins
            mask = (p[:, j] >= lo) & ((p[:, j] < hi) if hi < 1 else (p[:, j] <= hi))
            if mask.sum():
                rows.append({"Outcome": name, "Predicted range": f"{lo:.0%}–{hi:.0%}",
                             "Matches": int(mask.sum()),
                             "Mean predicted": float(p[mask, j].mean()),
                             "Observed frequency": float((y[mask] == j).mean()),
                             "Error (actual minus predicted)": float((y[mask] == j).mean() - p[mask, j].mean())})
    return pd.DataFrame(rows)
