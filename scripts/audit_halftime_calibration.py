"""Audit saved, out-of-sample halftime model predictions without retraining.

Input CSV columns: match_id, market, selection, predicted_probability, actual.
One row per market/selection/match. 'actual' must be 0 or 1.
Only use predictions recorded before the outcome was known.
"""
import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path

REQUIRED = {"match_id", "market", "selection", "predicted_probability", "actual"}

def audit(input_path, output_path):
    groups = defaultdict(list)
    seen = set()
    with open(input_path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not REQUIRED.issubset(reader.fieldnames):
            raise ValueError("Missing columns: " + ", ".join(sorted(REQUIRED - set(reader.fieldnames or []))))
        for line, row in enumerate(reader, 2):
            key = (row["match_id"], row["market"], row["selection"])
            if key in seen:
                raise ValueError(f"Duplicate prediction at line {line}: {key}")
            seen.add(key)
            p = float(row["predicted_probability"])
            if not math.isfinite(p) or not 0 <= p <= 1:
                raise ValueError(f"Invalid probability at line {line}")
            if row["actual"] not in ("0", "1"):
                raise ValueError(f"Actual must be 0 or 1 at line {line}")
            outcome = int(row["actual"])
            bucket = min(int(p * 10), 9)
            groups[(row["market"], row["selection"], bucket)].append((p, outcome))
    if not groups:
        raise ValueError("No prediction rows found")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["market", "selection", "probability_band", "n", "mean_predicted_pct",
                         "actual_pct", "difference_actual_minus_predicted_pp", "brier"])
        for (market, selection, bucket), values in sorted(groups.items()):
            n = len(values)
            predicted = sum(p for p, _ in values) / n
            actual = sum(y for _, y in values) / n
            brier = sum((p - y) ** 2 for p, y in values) / n
            writer.writerow([market, selection, f"{bucket * 10}-{(bucket + 1) * 10}%",
                             n, round(predicted * 100, 3), round(actual * 100, 3),
                             round((actual - predicted) * 100, 3), round(brier, 6)])
    return len(seen), len(groups)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="research_results/ht_calibration_audit.csv")
    args = parser.parse_args()
    n, groups = audit(args.input, args.output)
    print(f"Audited {n} predictions across {groups} market/selection/band groups.")
    print(f"Report: {args.output}")

if __name__ == "__main__":
    main()
