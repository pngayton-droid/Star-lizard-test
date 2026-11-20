"""Generate held-out predictions from the existing frozen halftime model.

Requires SUPABASE_URL and SUPABASE_SECRET_KEY. Only matches strictly AFTER the
model's last_training_date are evaluated. Never evaluate training rows.
"""
import csv
import io
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import requests

MODEL_URL = "https://raw.githubusercontent.com/pngayton-droid/Star-lizard-test/main/model_artifacts/halftime_second_half_models.joblib"
FIELDS = ["match_id", "market", "selection", "predicted_probability", "actual"]

def fetch_all(table, columns, key, url, filters=""):
    result = []
    for start in range(0, 30000, 500):
        response = requests.get(
            f"{url}/rest/v1/{table}?select={columns}{filters}",
            headers={"apikey": key, "Authorization": f"Bearer {key}",
                     "Range": f"{start}-{start + 499}"},
            timeout=60)
        response.raise_for_status()
        batch = response.json()
        result.extend(batch)
        if len(batch) < 500:
            break
    return result

def half_stat(stats, field, side):
    return float(stats["overview"][field]["first_half"][side])

def prices(payload):
    bookmakers = (payload or {}).get("data", {}).get("bookmakers", [])
    for book in sorted(bookmakers, key=lambda b: 0 if str(b.get("bookmaker", "")).lower() == "bet365" else 1):
        market = (book.get("markets") or {}).get("match_odds") or {}
        try:
            odds = [float(market[k]["last_seen"]) for k in ("home", "draw", "away")]
            if all(np.isfinite(v) and v > 1 for v in odds):
                return odds
        except (KeyError, TypeError, ValueError):
            pass
    return None

def features(row, stats, odds):
    hh, ah = int(row["home_ht_goals"]), int(row["away_ht_goals"])
    implied = np.array([1 / x for x in odds], dtype=float)
    ph, pd, pa = implied / implied.sum()
    diff = hh - ah
    return {
        "home_ht_goals": hh, "away_ht_goals": ah, "p_home": ph, "p_draw": pd,
        "p_away": pa, "ht_diff": diff, "ht_total": hh + ah,
        "score_strength": diff * (ph - pa),
        "h_shots": half_stat(stats, "total_shots", "home"),
        "a_shots": half_stat(stats, "total_shots", "away"),
        "h_sot": half_stat(stats, "shots_on_target", "home"),
        "a_sot": half_stat(stats, "shots_on_target", "away"),
        "h_corners": half_stat(stats, "corner_kicks", "home"),
        "a_corners": half_stat(stats, "corner_kicks", "away"),
        "h_red": half_stat(stats, "red_cards", "home"),
        "a_red": half_stat(stats, "red_cards", "away"),
        "home_ht_xg": float(row["home_ht_xg"]),
        "away_ht_xg": float(row["away_ht_xg"]),
    }

def outcomes(row):
    h = int(row["home_goals"]) - int(row["home_ht_goals"])
    a = int(row["away_goals"]) - int(row["away_ht_goals"])
    if min(h, a) < 0:
        raise ValueError("Negative second-half goals")
    # Next-goal ordering cannot be reconstructed from FT/HT totals.
    return {
        "over_0_5_2h": str(int(h + a >= 1)),
        "over_1_5_2h": str(int(h + a >= 2)),
        "over_2_5_2h": str(int(h + a >= 3)),
        "home_scores_2h": str(int(h >= 1)),
        "away_scores_2h": str(int(a >= 1)),
        "both_score_2h": str(int(h >= 1 and a >= 1)),
        "second_half_result": "home" if h > a else "away" if a > h else "draw",
    }

def reconcile(probs):
    o05 = probs["over_0_5_2h"]["1"]
    o15 = min(probs["over_1_5_2h"]["1"], o05)
    o25 = min(probs["over_2_5_2h"]["1"], o15)
    for name, p in (("over_0_5_2h", o05), ("over_1_5_2h", o15), ("over_2_5_2h", o25)):
        probs[name] = {"1": p, "0": 1 - p}
    nxt = probs["next_goal"]
    share = nxt["home"] / max(nxt["home"] + nxt["away"], 1e-12)
    probs["next_goal"] = {"home": o05 * share, "away": o05 * (1 - share), "none": 1 - o05}
    both = min(probs["both_score_2h"]["1"], probs["home_scores_2h"]["1"],
               probs["away_scores_2h"]["1"], o15)
    probs["both_score_2h"] = {"1": both, "0": 1 - both}
    h, a = probs["home_scores_2h"]["1"], probs["away_scores_2h"]["1"]
    excess = max(0., h + a - both - o05)
    if excess:
        rh, ra = max(0., h - both), max(0., a - both)
        take = min(rh, excess * rh / max(rh + ra, 1e-12))
        h -= take
        a -= min(ra, excess - take)
    probs["home_scores_2h"] = {"1": h, "0": 1 - h}
    probs["away_scores_2h"] = {"1": a, "0": 1 - a}
    draw = probs["second_half_result"]["draw"]
    if draw < 1 - o05:
        other = probs["second_half_result"]["home"] + probs["second_half_result"]["away"]
        factor = o05 / max(other, 1e-12)
        probs["second_half_result"] = {
            "home": probs["second_half_result"]["home"] * factor,
            "away": probs["second_half_result"]["away"] * factor, "draw": 1 - o05}
    return probs

def main():
    url = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SECRET_KEY"]
    model_response = requests.get(MODEL_URL, timeout=60)
    model_response.raise_for_status()
    # Trusted first-party model artifact only; joblib deserialization executes code.
    model = joblib.load(io.BytesIO(model_response.content))
    cutoff = str(model["last_training_date"])[:10]
    matches = fetch_all("historical_xg",
        "match_id,match_date,home_goals,away_goals,home_ht_goals,away_ht_goals,home_ht_xg,away_ht_xg",
        key, url, f"&match_date=gt.{cutoff}&order=match_date.asc")
    events = {r["match_id"]: r["stats_data"] for r in fetch_all(
        "historical_match_events", "match_id,stats_data", key, url)}
    odds = {r["match_id"]: r["odds_payload"] for r in fetch_all(
        "historical_match_odds", "match_id,odds_payload", key, url)}
    output = Path("research_results/ht_calibration_predictions.csv")
    output.parent.mkdir(parents=True, exist_ok=True)
    used = 0
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for row in matches:
            mid = row["match_id"]
            try:
                stats = events[mid]
                match_odds = prices(odds[mid])
                if not match_odds:
                    continue
                x = pd.DataFrame([features(row, stats, match_odds)])[model["feature_columns"]]
                scaled = model["scaler"].transform(x)
                predicted = {
                    market: {str(cls): float(p) for cls, p in zip(clf.classes_, clf.predict_proba(scaled)[0])}
                    for market, clf in model["models"].items()}
                predicted = reconcile(predicted)
                actual = outcomes(row)
                for market, winner in actual.items():
                    for selection, probability in predicted[market].items():
                        writer.writerow({"match_id": mid, "market": market,
                                         "selection": selection,
                                         "predicted_probability": probability,
                                         "actual": int(selection == winner)})
                used += 1
            except (KeyError, TypeError, ValueError, IndexError):
                continue
    print(f"Model training cutoff: {cutoff}; later matches: {len(matches)}; scored: {used}")
    if used == 0:
        raise RuntimeError("No genuine post-training matches with complete features and odds. "
                           "Do not substitute in-sample predictions.")

if __name__ == "__main__":
    main()
