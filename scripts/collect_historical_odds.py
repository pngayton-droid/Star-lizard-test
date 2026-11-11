"""Resumable historical odds backfill. Run with STATS_API_KEY, SUPABASE_URL,
SUPABASE_SECRET_KEY in a trusted server environment. No secrets in source control.

Examples:
  python scripts/collect_historical_odds.py --limit 20
  python scripts/collect_historical_odds.py --limit 12000
"""
import argparse
import os
import time
from datetime import datetime, timezone
import requests
from supabase import create_client

API_BASE = "https://api.thestatsapi.com/api"
PREFERRED = ("bet365", "betfair exchange", "pinnacle")
# Verified in actual historical responses: Bet365, Betfair Exchange, Pinnacle.
# William Hill was not returned in the initial 20-match sample.
def bookmaker_priority(name):
    normalized = name.lower().replace("_", " ").strip()
    if normalized == "bet365": return 0
    if normalized == "betfair exchange": return 1
    if normalized == "pinnacle": return 2
    if normalized == "betfair sportsbook": return 3
    return 4

def get_match_ids(db, limit):
    ids=[]
    offset=0
    while len(ids)<limit:
        page=(db.table("historical_xg").select("match_id")
              .like("match_id","mt_%").order("match_date",desc=True).range(offset,offset+999).execute().data or [])
        if not page: break
        ids.extend(str(row["match_id"]) for row in page if row.get("match_id"))
        offset+=len(page)
        if len(page)<1000: break
    return ids[:limit]

def fetch_odds(session, match_id):
    url=f"{API_BASE}/football/matches/{match_id}/odds"
    for attempt in range(4):
        response=session.get(url,timeout=30)
        if response.status_code==429:
            time.sleep(min(max(int(response.headers.get("Retry-After","30")),1),120))
            continue
        if response.status_code in (404,204):
            return "unavailable",None,None
        if response.status_code >= 400:
            try:
                error_text=str(response.json())[:250]
            except ValueError:
                error_text=response.text[:250]
            raise RuntimeError(f"API HTTP {response.status_code}: {error_text}")
        payload=response.json()
        data=payload.get("data") if isinstance(payload,dict) else None
        if not data:
            return "unavailable",payload,None
        books=data.get("bookmakers") if isinstance(data,dict) else None
        names=[str(b.get("bookmaker") or "") for b in books if isinstance(b,dict)] if isinstance(books,list) else []
        names=sorted(set(x for x in names if x),key=bookmaker_priority)
        return "collected",payload,names
    raise RuntimeError("Rate limit retries exhausted")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--limit",type=int,default=20)
    parser.add_argument("--interval",type=float,default=1.1)
    parser.add_argument("--retry-errors",action="store_true")
    args=parser.parse_args()
    if args.limit<1 or args.interval<1: parser.error("limit and interval must be positive; interval >=1 second")
    db=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])
    session=requests.Session()
    session.headers["Authorization"]="Bearer "+os.environ["STATS_API_KEY"]
    ids=get_match_ids(db,args.limit)
    done=0
    for index,match_id in enumerate(ids,1):
        existing=(db.table("historical_match_odds").select("fetch_status")
                  .eq("match_id",match_id).limit(1).execute().data or [])
        if existing and existing[0]["fetch_status"] in ("collected","unavailable"):
            continue
        if existing and existing[0]["fetch_status"]=="error" and not args.retry_errors:
            continue
        try:
            status,payload,names=fetch_odds(session,match_id)
            record={"match_id":match_id,"fetch_status":status,
                    "odds_payload":payload,"bookmaker_names":names or [],
                    "fetched_at":datetime.now(timezone.utc).isoformat(),
                    "error_message":None}
        except Exception as exc:
            record={"match_id":match_id,"fetch_status":"error",
                    "error_message":str(exc)[:300],
                    "fetched_at":datetime.now(timezone.utc).isoformat()}
        db.table("historical_match_odds").upsert(record,on_conflict="match_id").execute()
        done+=1
        print(f"{index}/{len(ids)} {match_id}: {record['fetch_status']}",flush=True)
        time.sleep(args.interval)
    print(f"New requests processed: {done}; candidates: {len(ids)}",flush=True)

if __name__=="__main__":main()
