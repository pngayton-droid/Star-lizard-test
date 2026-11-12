"""Read-only, single-match odds opening-price diagnostic."""
import json
import os
import sys
import requests

MATCH_ID = "mt_626386931"
URL = f"https://api.thestatsapi.com/api/football/matches/{MATCH_ID}/odds"

def main():
    key = os.environ.get("STATS_API_KEY")
    if not key:
        sys.exit("STATS_API_KEY secret is missing")
    response = requests.get(URL, headers={"Authorization": f"Bearer {key}"}, timeout=30)
    print(f"HTTP status: {response.status_code}")
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") or {}
    books = data.get("bookmakers") or []
    print(f"Match: {MATCH_ID}; bookmaker entries: {len(books)}")
    for book in books:
        if str(book.get("bookmaker", "")).strip().lower() != "bet365":
            continue
        markets = book.get("markets") or {}
        for market in ("match_odds", "btts", "total_goals", "match_corners", "asian_handicap"):
            selections = markets.get(market) or {}
            if not isinstance(selections, dict):
                continue
            counts = {"selections": 0, "opening_present": 0, "last_seen_present": 0}
            def visit(value):
                if not isinstance(value, dict):
                    return
                if "opening" in value or "last_seen" in value:
                    counts["selections"] += 1
                    counts["opening_present"] += value.get("opening") is not None
                    counts["last_seen_present"] += value.get("last_seen") is not None
                else:
                    for child in value.values():
                        visit(child)
            visit(selections)
            print(f"{market}: {json.dumps(counts)}")
        home = markets.get("match_odds", {}).get("home", {})
        print("Bet365 home 1X2 opening present:", home.get("opening") is not None)
        print("Bet365 home 1X2 last_seen present:", home.get("last_seen") is not None)
        return
    print("Bet365 not present in this response")

if __name__ == "__main__":
    main()
