"""Probe a small sample of older collected matches missing correct-score markets.
Never overwrite original historical odds; log results to Actions output.
"""
import os, time, json, random
import requests
from supabase import create_client

db=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])
session=requests.Session()
session.headers["Authorization"]="Bearer "+os.environ["STATS_API_KEY"]
rows=[]
for offset in range(0,12000,1000):
    page=(db.table("historical_match_odds").select("match_id,odds_payload,fetch_status")
          .eq("fetch_status","collected").order("match_id").range(offset,offset+999).execute().data or [])
    for row in page:
        payload=row.get("odds_payload") or {}
        books=(payload.get("data") or {}).get("bookmakers") or []
        if not any("correct_score" in (b.get("markets") or {}) for b in books):
            rows.append(row["match_id"])
    if len(page)<1000: break
random.Random(20261114).shuffle(rows)
sample=rows[:12]
print(f"Missing-correct-score candidates: {len(rows)}; probing {len(sample)}")
for i,mid in enumerate(sample,1):
    try:
        response=session.get(f"https://api.thestatsapi.com/api/football/matches/{mid}/odds",timeout=35)
        if response.status_code==429:
            delay=min(int(response.headers.get("Retry-After","30")),120)
            time.sleep(delay)
            response=session.get(f"https://api.thestatsapi.com/api/football/matches/{mid}/odds",timeout=35)
        response.raise_for_status()
        books=((response.json().get("data") or {}).get("bookmakers") or [])
        cs=[b.get("bookmaker") for b in books if "correct_score" in (b.get("markets") or {})]
        print(json.dumps({"sample":i,"match_id":mid,"correct_score_bookmakers":cs,"bookmakers":len(books)}),flush=True)
    except Exception as exc:
        print(json.dumps({"sample":i,"match_id":mid,"error":str(exc)[:160]}),flush=True)
    time.sleep(1.5)
