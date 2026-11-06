
import os
import json
import time
import requests
from supabase import create_client

# TEAM STARLIZARD — HISTORICAL EVENT INSPECTION
# Read-only: no database changes.
# Five matches, two API requests per match.

BASE = "https://api.thestatsapi.com/api"
API_KEY = os.environ["STATS_API_KEY"]

db = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SECRET_KEY"],
)

headers = {
    "Authorization": f"Bearer {API_KEY}"
}

# Pick matches across several seasons.
# Exclude legacy IDs.
result = (
    db.table("historical_xg")
    .select("match_id,match_date,home_team,away_team")
    .like("match_id", "mt_%")
    .not_.is_("home_goals", "null")
    .order("match_date", desc=True)
    .limit(1000)
    .execute()
)

matches = result.data or []

# Sample dates spread through the returned history.
positions = [0, 200, 400, 600, 800]
samples = [
    matches[i]
    for i in positions
    if i < len(matches)
]

print("TEAM STARLIZARD — EVENT INSPECTION", flush=True)
print(f"Matches selected: {len(samples)}", flush=True)

def inspect_endpoint(match, endpoint):
    match_id = match["match_id"]
    url = f"{BASE}/football/matches/{match_id}/{endpoint}"

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=30,
        )

        print(
            f"\nENDPOINT: {endpoint}"
            f"\nSTATUS: {response.status_code}",
            flush=True,
        )

        if response.status_code != 200:
            print(
                "ERROR RESPONSE:",
                response.text[:1500],
                flush=True,
            )
            return

        payload = response.json()

        # Print a bounded sample to avoid enormous logs.
        output = json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        )

        print(output[:12000], flush=True)

        if len(output) > 12000:
            print(
                "... RESPONSE TRUNCATED ...",
                flush=True,
            )

    except requests.RequestException as exc:
        print(f"REQUEST ERROR: {exc}", flush=True)

for index, match in enumerate(samples, 1):
    print(
        f"\n{'=' * 60}"
        f"\nMATCH {index}/{len(samples)}"
        f"\n{match['match_date']}"
        f"\n{match['home_team']} v {match['away_team']}"
        f"\nID: {match['match_id']}"
        f"\n{'=' * 60}",
        flush=True,
    )

    inspect_endpoint(match, "stats")
    time.sleep(1.2)

    inspect_endpoint(match, "timeline")
    time.sleep(1.2)

print("\nINSPECTION COMPLETE", flush=True)
