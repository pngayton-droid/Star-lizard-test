
"""PRO STARLIZARD — Red Card Diagnostic.

Read-only Supabase investigation.
No database writes or TheStatsAPI calls.
"""

import os
from collections import Counter
from supabase import create_client

PAGE_SIZE = 500


def get_stat(data, period, side):
    try:
        return data["overview"]["red_cards"][period][side]
    except (KeyError, TypeError):
        return None


def main():
    db = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SECRET_KEY"],
    )

    print("PRO STARLIZARD — RED CARD DIAGNOSTIC")
    print("=" * 65)

    rows = []
    offset = 0

    while True:
        response = (
            db.table("historical_match_events")
            .select("match_id,red_cards_match,stats_data")
            .order("match_id")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )

        batch = response.data or []
        rows.extend(batch)

        if len(batch) < PAGE_SIZE:
            break

        offset += PAGE_SIZE

    raw_counts = Counter()
    calculated_counts = Counter()
    mismatches = Counter()
    missing = 0
    valid = 0
    half_mismatches = 0
    examples = []

    for row in rows:
        raw = row.get("red_cards_match")
        raw_counts[str(raw)] += 1

        data = row.get("stats_data") or {}

        home = get_stat(data, "all", "home")
        away = get_stat(data, "all", "away")

        h1 = get_stat(data, "first_half", "home")
        a1 = get_stat(data, "first_half", "away")
        h2 = get_stat(data, "second_half", "home")
        a2 = get_stat(data, "second_half", "away")

        values = (home, away, h1, a1, h2, a2)

        if not all(
            isinstance(v, int) and not isinstance(v, bool)
            and v >= 0
            for v in values
        ):
            missing += 1
            continue

        valid += 1
        total = home + away
        calculated_counts[total] += 1

        if home != h1 + h2 or away != a1 + a2:
            half_mismatches += 1

        if raw is not None and raw != total:
            mismatches[(str(raw), str(total))] += 1

            if len(examples) < 5:
                examples.append({
                    "match_id": row["match_id"],
                    "stored_total": raw,
                    "calculated_total": total,
                    "home": home,
                    "away": away,
                })

    print("Records:", len(rows))
    print("Valid six-field red-card breakdowns:", valid)
    print("Incomplete or invalid breakdowns:", missing)

    print("\nSTORED red_cards_match DISTRIBUTION")
    for value, count in raw_counts.most_common(20):
        print(f"  {value}: {count}")

    print("\nCALCULATED RED-CARD TOTAL DISTRIBUTION")
    for value, count in sorted(calculated_counts.items()):
        print(f"  {value}: {count}")

    print("\nCHECKS")
    print("Half-by-half inconsistencies:", half_mismatches)
    print("Stored-versus-calculated mismatches:",
          sum(mismatches.values()))

    print("\nMOST COMMON MISMATCH TYPES")
    for pair, count in mismatches.most_common(10):
        print(
            f"  Stored {pair[0]} vs "
            f"calculated {pair[1]}: {count}"
        )

    print("\nFIVE MISMATCH EXAMPLES")
    for example in examples:
        print(example)

    print("\nDIAGNOSTIC COMPLETE")
    print("No records modified.")


if __name__ == "__main__":
    main()
