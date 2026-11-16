"""Audit saved TheStatsAPI odds without inventing quote timestamps.

Run in GitHub Actions or locally with SUPABASE_URL and SUPABASE_SECRET_KEY.
Does not call TheStatsAPI or alter any database rows.
"""
import json
import os
from collections import Counter
from supabase import create_client

db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET_KEY"])
counts = Counter()
keys = Counter()
book_keys = Counter()
examples = {}
offset = 0
while True:
    page = (db.table("historical_match_odds")
            .select("match_id,odds_payload,fetched_at")
            .range(offset, offset + 499).execute().data or [])
    if not page:
        break
    for row in page:
        counts["rows"] += 1
        payload = row.get("odds_payload") or {}
        data = payload.get("data") or {}
        if not isinstance(data, dict):
            counts["non_dict_data"] += 1
            continue
        keys.update(data.keys())
        books = data.get("bookmakers") or []
        if not isinstance(books, list):
            counts["non_list_bookmakers"] += 1
            continue
        for book in books:
            if not isinstance(book, dict):
                continue
            name = str(book.get("bookmaker", ""))
            if name.lower() not in ("bet365", "pinnacle", "betfair exchange"):
                continue
            book_keys.update(book.keys())
            markets = book.get("markets") or {}
            match_odds = markets.get("match_odds") or {}
            if not isinstance(match_odds, dict):
                continue
            for side in ("home", "draw", "away"):
                quote = match_odds.get(side) or {}
                if isinstance(quote, dict):
                    for field in quote:
                        counts[f"{name}:{side}:{field}"] += 1
            if name not in examples:
                # Only structural information; never print tokens or full raw payloads.
                examples[name] = {
                    "bookmaker_fields": sorted(book.keys()),
                    "match_odds_fields": sorted(match_odds.keys()),
                    "home_quote_fields": sorted((match_odds.get("home") or {}).keys()),
                }
    offset += len(page)
    if len(page) < 500:
        break
print(json.dumps({
    "records": counts["rows"],
    "data_keys": dict(keys),
    "bookmaker_keys": dict(book_keys),
    "quote_field_counts": {k:v for k,v in counts.items() if ":" in k},
    "structural_examples": examples,
    "note": "fetched_at is retrieval time, not quote time; last_seen must not be relabelled as observed_at"
}, indent=2, sort_keys=True))
