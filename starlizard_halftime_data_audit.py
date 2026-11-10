
"""PRO STARLIZARD — Halftime Historical Data Audit.

Read-only Supabase schema and coverage inspection.
No database writes or TheStatsAPI requests.
Does not print credentials or individual match records.
"""

import os
from supabase import create_client


def main():
    db = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SECRET_KEY"],
    )

    print("PRO STARLIZARD — HALFTIME DATA AUDIT")
    print("=" * 48)

    # Start with the table already used by our pricing engine.
    table = "historical_xg"

    print(f"\nTABLE: {table}")

    try:
        result = (
            db.table(table)
            .select("*", count="exact")
            .limit(1)
            .execute()
        )

        rows = result.data or []

        print(f"Total records: {result.count}")

        if not rows:
            print("No records available.")
            return

        columns = sorted(rows[0].keys())

        print("\nAVAILABLE COLUMNS")
        for column in columns:
            print(f"  {column}")

        print("\nHALFTIME FIELD CHECK")

        keywords = (
            "half",
            "ht_",
            "xg",
            "goal",
            "minute",
            "event",
            "odds",
            "corner",
            "card",
            "red",
            "shot",
            "score",
        )

        matching = [
            col for col in columns
            if any(word in col.lower() for word in keywords)
        ]

        if matching:
            for column in matching:
                print(f"  FOUND: {column}")
        else:
            print("No matching halftime-related columns.")

        print("\nFIELD COVERAGE IN THIS TABLE")

        # Count populated values across all rows for each
        # relevant column without downloading match data.
        for column in matching:
            try:
                response = (
                    db.table(table)
                    .select(column, count="exact")
                    .not_.is_(column, "null")
                    .limit(0)
                    .execute()
                )
                print(
                    f"  {column}: "
                    f"{response.count} non-null records"
                )
            except Exception as exc:
                print(
                    f"  {column}: count unavailable "
                    f"({type(exc).__name__})"
                )

    except Exception as exc:
        print(
            f"Audit failed: {type(exc).__name__}: {exc}"
        )
        raise

    print("\nAUDIT COMPLETE")
    print(
        "This checks historical_xg only. "
        "Other timeline/event tables still need inspection."
    )
    print("No records were modified.")


if __name__ == "__main__":
    main()
