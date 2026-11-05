import os
import json
import requests
from supabase import create_client

BASE = "https://api.thestatsapi.com/api"

API_KEY = os.environ["STATS_API_KEY"]

db = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SECRET_KEY"]
)

headers = {
    "Authorization": f"Bearer {API_KEY}"
}

print("PRO STAR LIZARD - MATCH RESULTS INVESTIGATION")

result = (
    db.table("historical_xg")
    .select("match_id,match_date,home_team,away_team")
    .like("match_id", "mt_%")
    .order("match_date", desc=True)
    .limit(1)
    .execute()
)

matches = result.data or []

print(f"Matches selected: {len(matches)}")

for match in matches:
    match_id = match["match_id"]

    print("\n" + "=" * 60)
    print(
        match["match_date"],
        match["home_team"],
        "v",
        match["away_team"]
    )
    print("MATCH ID:", match_id)

    response = requests.get(
        f"{BASE}/football/matches/{match_id}",
        headers=headers,
        timeout=30
    )

    print("HTTP STATUS:", response.status_code)

    if response.ok:
        payload = response.json()

        print("MATCH API RESPONSE:")
        print(json.dumps(payload, indent=2))
    else:
        print("API ERROR:", response.text[:1000])

print("\nINVESTIGATION FINISHED")
