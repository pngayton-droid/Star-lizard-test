"""Pure, dependency-light historical evaluation functions for Starlizard 2.0.

No provider calls. No model training on evaluation-period matches.
Do not interpret outcome frequencies as betting profitability.
"""
from datetime import date
from math import sqrt
from typing import Iterable


def wilson_interval(hits: int, n: int, z: float = 1.96):
    """Two-sided approximate 95% binomial confidence interval."""
    if n <= 0 or hits < 0 or hits > n:
        return (None, None)
    p = hits / n
    d = 1 + z*z/n
    centre = (p + z*z/(2*n))/d
    radius = z*sqrt(p*(1-p)/n + z*z/(4*n*n))/d
    return max(0.0, centre-radius), min(1.0, centre+radius)


def chronological_split(rows: Iterable[dict], train_fraction: float = 0.70):
    """Sort by match date; hold out *entire dates* to avoid same-day leakage.

    Rows must contain 'match_id' and ISO 'match_date'; duplicates and missing
    dates are rejected. Returns (train, test, split_date). No shuffling.
    """
    if not 0 < train_fraction < 1:
        raise ValueError("train_fraction must be between zero and one")
    seen = set()
    ordered = []
    for row in rows:
        match_id = str(row.get("match_id", ""))
        raw_date = row.get("match_date")
        if not match_id or not raw_date:
            raise ValueError("All rows need match_id and match_date")
        if match_id in seen:
            raise ValueError(f"Duplicate match_id: {match_id}")
        seen.add(match_id)
        date_value = date.fromisoformat(str(raw_date)[:10])
        ordered.append((date_value, match_id, row))
    if len(ordered) < 2:
        raise ValueError("At least two matches required")
    ordered.sort(key=lambda item: (item[0], item[1]))
    unique_dates = sorted({item[0] for item in ordered})
    if len(unique_dates) < 2:
        raise ValueError("At least two distinct match dates required")
    # Pick a date boundary near the target fraction, never split a date.
    candidate_dates = unique_dates[1:]
    # One linear scan of date boundaries; avoid quadratic work on large archives.
    date_counts = {}
    for day, _, _ in ordered:
        date_counts[day] = date_counts.get(day, 0) + 1
    cumulative = 0
    best_error = float("inf")
    split = candidate_dates[0]
    for previous_day, day in zip(unique_dates, unique_dates[1:]):
        cumulative += date_counts[previous_day]
        error = abs(cumulative / len(ordered) - train_fraction)
        if error < best_error:
            best_error, split = error, day
    train = [item[2] for item in ordered if item[0] < split]
    test = [item[2] for item in ordered if item[0] >= split]
    return train, test, split.isoformat()


def evaluate_binary_baseline(train, test, outcome: str, min_train: int = 100):
    """Predict test events using only the historical training frequency.

    This is a calibration baseline, not a trading strategy.
    """
    training = [int(r[outcome]) for r in train if r.get(outcome) is not None]
    testing = [int(r[outcome]) for r in test if r.get(outcome) is not None]
    if any(v not in (0, 1) for v in training + testing):
        raise ValueError("Outcomes must be binary")
    if len(training) < min_train or not testing:
        return None
    p = sum(training) / len(training)
    observed = sum(testing) / len(testing)
    brier = sum((p-y)**2 for y in testing)/len(testing)
    lower, upper = wilson_interval(sum(testing), len(testing))
    return {
        "train_n": len(training), "test_n": len(testing),
        "train_rate": p, "test_rate": observed,
        "test_wilson_low": lower, "test_wilson_high": upper,
        "test_brier": brier,
        "test_baseline_brier": sum((sum(testing)/len(testing)-y)**2 for y in testing)/len(testing),
    }


def test_self():
    assert wilson_interval(0, 0) == (None, None)
    lo, hi = wilson_interval(50, 100)
    assert lo < .5 < hi
    rows = [
        {"match_id": str(i), "match_date": f"2026-01-{(i//2)+1:02d}", "win": i % 2}
        for i in range(20)
    ]
    train, test, split_date = chronological_split(rows)
    assert max(r["match_date"] for r in train) < min(r["match_date"] for r in test)
    assert len(train) + len(test) == 20
    result = evaluate_binary_baseline(train, test, "win", min_train=2)
    assert result is not None and result["train_n"] + result["test_n"] == 20
    return "PASS"


if __name__ == "__main__":
    print(test_self())
