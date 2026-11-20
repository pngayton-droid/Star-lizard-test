"""Chronological 2,000-match retrospective calibration with an earlier refitted model.

This is NOT an audit of the currently deployed frozen model. It uses the same
dashboard features and a fresh logistic-regression baseline fitted on earlier
matches only. No production model is modified.
"""
import csv
import os
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from generate_ht_calibration_predictions import fetch_all, features, outcomes, prices, reconcile

FEATURES = [
    "home_ht_goals", "away_ht_goals", "p_home", "p_draw", "p_away",
    "ht_diff", "ht_total", "score_strength", "h_shots", "a_shots",
    "h_sot", "a_sot", "h_corners", "a_corners", "h_red", "a_red",
    "home_ht_xg", "away_ht_xg",
]
MARKETS = [
    "over_0_5_2h", "over_1_5_2h", "over_2_5_2h",
    "home_scores_2h", "away_scores_2h", "both_score_2h",
    "second_half_result",
]

def main():
    url = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SECRET_KEY"]
    matches = fetch_all(
        "historical_xg",
        "match_id,match_date,home_goals,away_goals,home_ht_goals,away_ht_goals,home_ht_xg,away_ht_xg",
        key, url, "&order=match_date.asc,match_id.asc")
    events = {r["match_id"]: r["stats_data"] for r in fetch_all(
        "historical_match_events", "match_id,stats_data", key, url)}
    odds = {r["match_id"]: r["odds_payload"] for r in fetch_all(
        "historical_match_odds", "match_id,odds_payload", key, url)}
    records = []
    skipped = 0
    for row in matches:
        mid = row["match_id"]
        try:
            if any(row[k] is None for k in (
                "match_date", "home_goals", "away_goals", "home_ht_goals",
                "away_ht_goals", "home_ht_xg", "away_ht_xg")):
                skipped += 1
                continue
            quote = prices(odds[mid])
            if quote is None:
                skipped += 1
                continue
            x = features(row, events[mid], quote)
            if not all(np.isfinite(float(v)) for v in x.values()):
                skipped += 1
                continue
            records.append((str(row["match_date"]), str(mid), x, outcomes(row)))
        except (KeyError, TypeError, ValueError, IndexError, OverflowError):
            skipped += 1
    records.sort(key=lambda r: (r[0], r[1]))
    if len(records) < 3000:
        raise RuntimeError(f"Only {len(records)} complete historical matches; need >=3000")
    # Keep same-day fixtures together to avoid training on outcomes from test day.
    target = records[-2000][0]
    train = [r for r in records if r[0] < target]
    test = [r for r in records if r[0] >= target]
    if len(train) < 1000 or len(test) < 1000:
        raise RuntimeError("Insufficient strict chronological training/test split")
    scaler = StandardScaler()
    x_train = scaler.fit_transform(pd.DataFrame([r[2] for r in train])[FEATURES])
    x_test = scaler.transform(pd.DataFrame([r[2] for r in test])[FEATURES])
    predicted = {}
    for market in MARKETS:
        y_train = [r[3][market] for r in train]
        if len(set(y_train)) < 2:
            raise RuntimeError(f"Single class in training data: {market}")
        clf = LogisticRegression(max_iter=2000, C=1.0)
        clf.fit(x_train, y_train)
        values = clf.predict_proba(x_test)
        predicted[market] = [
            {str(cls): float(p) for cls, p in zip(clf.classes_, row)}
            for row in values
        ]
    output = Path("research_results/ht_calibration_predictions.csv")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["match_id", "market", "selection",
                           "predicted_probability", "actual"])
        writer.writeheader()
        for i, (_, mid, _, actual) in enumerate(test):
            # Use the exact seven-market coherence adjustments from the dashboard.
            # Next goal is excluded: goal order requires verified timeline data.
            probs = {market: predicted[market][i] for market in MARKETS}
            # Reconcile using a dummy next-goal distribution solely to reproduce
            # other market constraints; no next-goal probabilities are reported.
            probs["next_goal"] = {"home": 0.4, "away": 0.4, "none": 0.2}
            probs = reconcile(probs)
            for market in MARKETS:
                for selection, p in probs[market].items():
                    writer.writerow({
                        "match_id": mid, "market": market,
                        "selection": selection, "predicted_probability": p,
                        "actual": int(selection == actual[market]),
                    })
    print(f"Total historical rows: {len(matches)}; complete: {len(records)}; skipped: {skipped}")
    print(f"TRAIN: {len(train)} matches through {train[-1][0]}")
    print(f"TEST: {len(test)} matches from {test[0][0]} through {test[-1][0]}")
    print(f"Generated: {output}")
    print("Method: fresh chronological logistic regression, NOT deployed model.")
    print("Next-goal excluded until timeline ordering is validated.")

if __name__ == "__main__":
    main()
