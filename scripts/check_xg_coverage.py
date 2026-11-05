
import os
import json
import requests

BASE = "https://api.thestatsapi.com/api"
API_KEY = os.environ["STATS_API_KEY"]

LEAGUES = {
    "Premier League": "comp_3039",
    "Championship": "comp_8321",
    "La Liga": "comp_8814",
    "Serie A": "comp_5840",
    "Bundesliga": "comp_4643",
    "Ligue 1": "comp_0256",
    "Eredivisie": "comp_3809",
    "Primeira Liga": "comp_8385",
    "Belgian Pro League": "comp_8531",
    "Scottish Premiership": "comp_6387",
}

headers = {
    "Authorization": f"Bearer {API_KEY}"
}

print("PRO STAR LIZARD - HISTORICAL COVERAGE AUDIT")

for name, competition_id in LEAGUES.items():
    print(f"\n{'=' * 50}")
    print(f"LEAGUE: {name}")
    print(f"COMPETITION ID: {competition_id}")

    try:
        response = requests.get(
            f"{BASE}/coverage/leagues/{competition_id}",
            headers=headers,
            timeout=30,
        )

        print(f"HTTP STATUS: {response.status_code}")

        if response.ok:
            data = response.json()
            print(json.dumps(data, indent=2))
        else:
            print("Coverage request unsuccessful")
            print(response.text[:1000])

    except requests.RequestException as error:
        print(f"REQUEST ERROR: {error}")

print("\nHISTORICAL COVERAGE AUDIT FINISHED")
