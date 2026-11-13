"""Chronological categorical calibration for football match outcomes.

Only pre-event information may be used as feature values. Training and evaluation
must use nonoverlapping match dates. No odds assumptions and no provider calls.
"""
from collections import defaultdict


def smoothed_rate(successes, n, prior_rate, strength=30.0):
    if n < 0 or successes < 0 or successes > n:
        raise ValueError("Invalid success counts")
    if not 0 <= prior_rate <= 1 or strength < 0:
        raise ValueError("Invalid prior")
    if n + strength == 0:
        return prior_rate
    return (successes + strength * prior_rate) / (n + strength)


def fit_conditional_rates(train, feature_names, outcome, prior_strength=30):
    """Fit only on earlier records; shrink small groups to global training rate."""
    observations = [r for r in train if r.get(outcome) in (0, 1)]
    if not observations:
        raise ValueError("No valid training outcomes")
    prior = sum(r[outcome] for r in observations) / len(observations)
    groups = defaultdict(lambda: [0, 0])
    for row in observations:
        key = tuple(str(row.get(name, "Missing")) for name in feature_names)
        groups[key][0] += int(row[outcome])
        groups[key][1] += 1
    return {"prior": prior, "strength": float(prior_strength),
            "features": tuple(feature_names), "groups": dict(groups),
            "train_n": len(observations)}


def predict(model, row):
    key = tuple(str(row.get(name, "Missing")) for name in model["features"])
    wins, n = model["groups"].get(key, (0, 0))
    return smoothed_rate(wins, n, model["prior"], model["strength"]), n


def evaluate(model, test, outcome):
    """Brier and log-free diagnostics on untouched later matches."""
    evaluated = []
    for row in test:
        y = row.get(outcome)
        if y not in (0, 1):
            continue
        p, n = predict(model, row)
        evaluated.append((int(y), p, n))
    if not evaluated:
        return None
    prior = model["prior"]
    return {
        "train_n": model["train_n"],
        "test_n": len(evaluated),
        "model_brier": sum((p-y)**2 for y,p,_ in evaluated)/len(evaluated),
        "global_train_baseline_brier": sum((prior-y)**2 for y,_,_ in evaluated)/len(evaluated),
        "observed_rate": sum(y for y,_,_ in evaluated)/len(evaluated),
        "predicted_rate": sum(p for _,p,_ in evaluated)/len(evaluated),
        "unseen_group_test_n": sum(n == 0 for _,_,n in evaluated),
    }


def calibration_bins(model, test, outcome, bin_count=5):
    """Group predictions into fixed probability bins, without fitting on test.

    Counts and observed rates are diagnostic only; empty bins are omitted.
    """
    if not isinstance(bin_count, int) or bin_count < 2:
        raise ValueError("bin_count must be an integer >= 2")
    buckets = [[0, 0.0, 0] for _ in range(bin_count)]
    for row in test:
        y = row.get(outcome)
        if y not in (0, 1):
            continue
        p, _ = predict(model, row)
        index = min(int(p * bin_count), bin_count - 1)
        bucket = buckets[index]
        bucket[0] += 1
        bucket[1] += p
        bucket[2] += int(y)
    return [
        {"Probability band": f"{100*i//bin_count}-{100*(i+1)//bin_count}%",
         "Matches": n, "Predicted %": round(100*sum_p/n, 2),
         "Observed %": round(100*hits/n, 2)}
        for i, (n, sum_p, hits) in enumerate(buckets) if n
    ]
