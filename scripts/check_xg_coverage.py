import os
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

headers = {"Authorization": f"Bearer {API_KEY}"}

print("\nPRO STAR LIZARD - xG COVERAGE SUMMARY")
print("=" * 75)
print(
    f"{'LEAGUE':<23} "
    f"{'EARLIEST':<12} "
    f"{'SEASONS':<9} "
    f"{'xG MATCHES':<12}"
)
print("-" * 75)

for name, competition_id in LEAGUES.items():
    try:
        response = requests.get(
            f"{BASE}/coverage/leagues/{competition_id}",
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()

        seasons = response.json().get("data", {}).get(
            "seasons", []
        )

        covered = []

        for season in seasons:
            xg = season.get("data_types", {}).get("xg", {})

            if xg.get("covered_events", 0) > 0:
                covered.append(season)

        if covered:
            earliest = min(
                covered,
                key=lambda s: int(s["year"].split("/")[0])
            )["year"]

            total_matches = sum(
                s["data_types"]["xg"]["covered_events"]
                for s in covered
            )

            print(
                f"{name:<23} "
                f"{earliest:<12} "
                f"{len(covered):<9} "
                f"{total_matches:<12}"
            )
        else:
            print(
                f"{name:<23} "
                f"{'NONE':<12} "
                f"{0:<9} "
                f"{0:<12}"
            )

    except Exception as error:
        print(f"{name:<23} ERROR: {error}")

print("=" * 75)
print("Coverage is provider-reported xG, not verified HT xG.")
print("AUDIT COMPLETE")
