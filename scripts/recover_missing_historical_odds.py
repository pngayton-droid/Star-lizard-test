"""One-off bounded recovery of missing historical odds only."""
import os,time,requests
from datetime import datetime,timezone
from supabase import create_client
DB=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])
S=requests.Session()
S.headers["Authorization"]="Bearer "+os.environ["STATS_API_KEY"]
MAX_CALLS=90
MIN_REMAINING=500
calls=0
def pages(table,columns):
    out=[];offset=0
    while True:
        chunk=DB.table(table).select(columns).order("match_id").range(offset,offset+999).execute().data or []
        out.extend(chunk)
        if len(chunk)<1000:return out
        offset+=len(chunk)
def main():
    global calls
    existing={r["match_id"]:r for r in pages("historical_match_odds","match_id,fetch_status,odds_payload")}
    matches=pages("historical_xg","match_id,match_date")
    missing=[m for m in matches if m["match_id"].startswith("mt_") and (m["match_id"] not in existing or existing[m["match_id"]].get("odds_payload") is None)]
    print("MISSING_ODDS_CANDIDATES",len(missing),flush=True)
    saved=unavailable=errors=0
    for m in missing:
        mid=m["match_id"]
        if calls>=MAX_CALLS:
            print("STOP_REQUEST_BUDGET",calls,flush=True);break
        try:
            r=S.get(f"https://api.thestatsapi.com/api/football/matches/{mid}/odds",timeout=40)
            calls+=1
            remaining=r.headers.get("X-Monthly-Quota-Remaining")
            if remaining and remaining.isdigit() and int(remaining)<=MIN_REMAINING:
                print("STOP_QUOTA_FLOOR",remaining,flush=True);break
            if r.status_code==429:
                print("STOP_RATE_LIMIT",mid,flush=True);break
            if r.status_code in (401,403):
                print("STOP_AUTH",r.status_code,flush=True);break
            payload=r.json() if r.status_code==200 else None
            data=payload.get("data") if isinstance(payload,dict) else None
            books=data.get("bookmakers") if isinstance(data,dict) else None
            if isinstance(books,list) and books:
                names=sorted(set(str(b.get("bookmaker") or b.get("name") or "") for b in books if isinstance(b,dict)))
                status="collected";saved+=1
            else:
                status="unavailable";names=[];unavailable+=1
            record={"match_id":mid,"fetch_status":status,"odds_payload":payload if status=="collected" else None,"bookmaker_names":names,"fetched_at":datetime.now(timezone.utc).isoformat(),"error_message":None if r.status_code in (200,204,404) else f"HTTP {r.status_code}"}
            DB.table("historical_match_odds").upsert(record,on_conflict="match_id").execute()
            print("ODDS",mid,status,r.status_code,flush=True)
        except Exception as exc:
            errors+=1
            print("ERROR",mid,type(exc).__name__,str(exc)[:160],flush=True)
            if errors>=3:break
        time.sleep(1.5)
    print("SUMMARY",{"requests":calls,"saved":saved,"unavailable":unavailable,"errors":errors},flush=True)
if __name__=="__main__":main()
