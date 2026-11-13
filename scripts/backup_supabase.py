
import os
import json
from datetime import datetime, timezone
from pathlib import Path

from supabase import create_client

# Connect using GitHub's existing secrets.
db = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SECRET_KEY"],
)

# Our existing football database tables.
TABLES = [
    "historical_xg",
    "historical_match_odds",
    "historical_match_events",
    "collector_progress",
    "historical_xg_legacy_backup",
    "starlizard_next_goal_research",
    "archive_football_data",
    "archive_source_links",
    "archive_understat",
    "archive_understat_goal_events",
    "pattern_scan_history",
]
PAGE_SIZE = 500
backup_dir = Path("backup_output")
backup_dir.mkdir(exist_ok=True)

manifest = {
    "created_at": datetime.now(timezone.utc).isoformat(),
    "tables": {},
}

for table in TABLES:
    print(f"Backing up {table}...", flush=True)

    # Count records before exporting.
    count_response = (
        db.table(table)
        .select("*", count="exact", head=True)
        .execute()
    )
    expected = count_response.count
    if expected is None:
        raise RuntimeError(f"Cannot verify count for {table}")

    rows = []
    offset = 0

    while offset < expected:
        response = (
            db.table(table)
            .select("*")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )

        batch = response.data or []

        if not batch:
            raise RuntimeError(
                f"Incomplete export for {table} at row {offset}"
            )

        rows.extend(batch)
        offset += len(batch)

        print(f"  Retrieved {len(rows)}/{expected}", flush=True)

    if len(rows) != expected:
        raise RuntimeError(
            f"Count mismatch for {table}: "
            f"expected {expected}, got {len(rows)}"
        )

    output_file = backup_dir / f"{table}.json"

    with output_file.open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2, default=str)

    manifest["tables"][table] = {
        "rows": len(rows),
        "file": output_file.name,
    }

with (backup_dir / "manifest.json").open("w") as f:
    json.dump(manifest, f, indent=2)

print("Backup export completed successfully.", flush=True)
