
"""PRO STARLIZARD — Event Structure Audit.

Inspect JSON shapes and coverage for goals, corners and cards.
Read-only. No external API requests or database writes.
"""

import os
from collections import Counter
from supabase import create_client


def describe(value, prefix="", depth=0):
    """Print structure, not individual match values."""
    if depth > 3:
        return

    if isinstance(value, dict):
        for key, item in list(value.items())[:40]:
            path = f"{prefix}.{key}" if prefix else str(key)
            print(f"  {path}: {type(item).__name__}")

            if isinstance(item, (dict, list)):
                describe(item, path, depth + 1)

    elif isinstance(value, list):
        print(f"  {prefix}: list")

        if value:
            describe(value[0], prefix + "[item]", depth + 1)


def main():
    db = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SECRET_KEY"],
    )

    print("PRO STARLIZARD — EVENT STRUCTURE AUDIT")
    print("=" * 65)

    table = "historical_match_events"

    rows = []
    offset = 0

    while True:
        response = (
            db.table(table)
            .select(
                "match_id,stats_status,timeline_status,"
                "stats_data,timeline_data,"
                "corners_match,yellow_cards_match,"
                "red_cards_match"
            )
            .order("match_id")
            .range(offset, offset + 499)
            .execute()
        )

        batch = response.data or []
        rows.extend(batch)

        if len(batch) < 500:
            break

        offset += 500

    print("Records:", len(rows))
    print("Unique match IDs:", len({
        row["match_id"] for row in rows
    }))

    for field in ("stats_status", "timeline_status"):
        counts = Counter(str(row.get(field)) for row in rows)

        print(f"\n{field.upper()}")

        for status, count in counts.most_common():
            print(f"  {status}: {count}")

    for field in ("stats_data", "timeline_data"):
        values = [
            row[field] for row in rows
            if row.get(field) is not None
        ]

        print(f"\n{field.upper()}")
        print("Non-null:", len(values))

        types = Counter(type(v).__name__ for v in values)
        print("JSON types:", dict(types))

        sample = next(
            (
                value for value in values
                if isinstance(value, (dict, list))
                and len(value) > 0
            ),
            None
        )

        if sample is not None:
            print("STRUCTURE (keys and types only):")
            describe(sample)
        else:
            print("No populated JSON structure found.")

    for field in (
        "corners_match",
        "yellow_cards_match",
        "red_cards_match",
    ):
        values = [row.get(field) for row in rows]
        present = [v for v in values if v is not None]

        print(f"\n{field.upper()}")
        print("Non-null:", len(present))
        print("Zero values:", sum(v == 0 for v in present))

    print("\nAUDIT COMPLETE")
    print("No match-level values printed.")
    print("No database records modified.")


if __name__ == "__main__":
    main()
