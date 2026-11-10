
"""PRO STARLIZARD — Unified Data Audit v1.

Inspect existing historical goals, corners, cards and
next-goal research tables.

READ ONLY:
- No database modifications
- No TheStatsAPI requests
- No credentials or match-level records printed
"""

import os
from supabase import create_client


TABLES = [
    "historical_xg",
    "historical_match_events",
    "starlizard_next_goal_research",
    "starlizard_verified_next_goal",
]

KEYWORDS = (
    "match", "team", "competition", "date",
    "goal", "score", "minute", "period",
    "half", "ht_", "xg", "shot",
    "corner", "card", "yellow", "red",
    "referee", "odds", "event",
)


def inspect_table(db, table):
    print("\n" + "=" * 65)
    print("TABLE:", table)
    print("=" * 65)

    try:
        result = (
            db.table(table)
            .select("*", count="exact")
            .limit(1)
            .execute()
        )
    except Exception as exc:
        print("STATUS: Not accessible")
        print("Reason:", type(exc).__name__)
        print("This does not necessarily mean the table is absent.")
        return

    print("STATUS: Accessible")
    print("Total records:", result.count)

    rows = result.data or []

    if not rows:
        print("No sample row available.")
        return

    columns = sorted(rows[0].keys())

    print("\nAVAILABLE COLUMNS")

    for column in columns:
        print(" ", column)

    print("\nPOTENTIAL JOIN / MARKET FIELDS")

    matching = [
        column for column in columns
        if any(
            keyword in column.lower()
            for keyword in KEYWORDS
        )
    ]

    for column in matching:
        print(" ", column)

    print("\nNON-NULL FIELD COVERAGE")

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
                f"{response.count} non-null"
            )

        except Exception as exc:
            print(
                f"  {column}: unavailable "
                f"({type(exc).__name__})"
            )


def main():
    print("PRO STARLIZARD — UNIFIED DATA AUDIT")
    print("=" * 65)

    db = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SECRET_KEY"],
    )

    for table in TABLES:
        inspect_table(db, table)

    print("\n" + "=" * 65)
    print("AUDIT COMPLETE")
    print("=" * 65)
    print("No records modified.")
    print("No TheStatsAPI requests made.")
    print(
        "Next: establish verified match joins "
        "and market data coverage."
    )


if __name__ == "__main__":
    main()
