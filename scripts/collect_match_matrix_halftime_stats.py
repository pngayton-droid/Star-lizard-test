"""Bounded, once-per-match first-half statistics snapshots from cached fixtures.
Runs in the existing five-minute prematch workflow; no fixture API calls.
"""
import os, json, datetime as dt
from pathlib import Path
import requests
from supabase import create_client

BASE="https://api.thestatsapi.com/api"
LEAGUES={"comp_3039","comp_8321","comp_8814","comp_5840","comp_4643","comp_0256","comp_3809","comp_8385","comp_8531","comp_6387"}
CACHE=Path(".cache/scanner_fixture_schedule.json")
TABLE="match_matrix_halftime_stats"
CAP=24
now=dt.datetime.now(dt.timezone.utc)
session=requests.Session()
session.headers["Authorization"]="Bearer "+os.environ["STATS_API_KEY"]
db=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])

def cid(m):
    comp=m.get("competition") or {}
    return str(m.get("competition_id") or (comp.get("id") if isinstance(comp,dict) else "") or "")

def ht_score(m):
    score=m.get("score") or {}
    for item in (score.get("half_time"),score.get("halftime"),score.get("halfTime"),m.get("half_time_score"),m.get("halfTime")):
        if isinstance(item,dict) and item.get("home") is not None and item.get("away") is not None:
            return {"home":int(item["home"]),"away":int(item["away"])}
    return None

def main():
    if not CACHE.is_file():
        print("No cached fixture schedule; skip halftime collection without API calls")
        return
    data=json.loads(CACHE.read_text())
    if data.get("date")!=now.date().isoformat():
        print("Cached fixture schedule is not for today; skip")
        return
    eligible=[]
    for m in data.get("matches") or []:
        if cid(m) not in LEAGUES:continue
        try:
            ko=dt.datetime.fromisoformat(str(m["utc_date"]).replace("Z","+00:00"))
            minutes=(now-ko).total_seconds()/60
        except (KeyError,TypeError,ValueError):continue
        # First-half data may arrive late. Keep a narrow window, and
        # label these as first-half snapshots, not guaranteed HT live odds.
        if 45<=minutes<=58 and m.get("id"):
            eligible.append((ko,m))
    eligible.sort(key=lambda x:x[0])
    print("First-half stats candidates:",len(eligible),"cap:",CAP)
    calls=saved=0
    for ko,m in eligible:
        if calls>=CAP:break
        mid=str(m["id"])
        existing=db.table(TABLE).select("match_id").eq("match_id",mid).limit(1).execute().data or []
        if existing:continue
        # Cached status is stale; verify actual halftime before capturing.
        if calls+2>CAP:break
        detail=session.get(f"{BASE}/football/matches/{mid}",timeout=25)
        calls+=1
        if detail.status_code in (404,409,429):
            print("Live match status unavailable:",mid,detail.status_code)
            if detail.status_code==429:break
            continue
        detail.raise_for_status()
        live=detail.json().get("data") or {}
        status=str(live.get("status") or "").lower().replace("-","_").replace(" ","_")
        if status not in {"ht","half_time","halftime"}:
            print("Not confirmed halftime:",mid,status)
            continue
        score=ht_score(live)
        if score is None:
            print("No verified halftime score:",mid)
            continue
        resp=session.get(f"{BASE}/football/matches/{mid}/stats",timeout=30)
        calls+=1
        if resp.status_code in (404,409,429):
            print("Stats unavailable:",mid,resp.status_code)
            if resp.status_code==429:break
            continue
        resp.raise_for_status()
        payload=resp.json().get("data") or {}
        ov=payload.get("overview") or {} if isinstance(payload,dict) else {}
        first={}
        for field in ("expected_goals","total_shots","shots_on_target","corner_kicks","red_cards"):
            block=(ov.get(field) or {}).get("first_half") or {}
            if isinstance(block,dict) and block.get("home") is not None and block.get("away") is not None:
                first[field]={"home":block["home"],"away":block["away"]}
        if len(first)<5:
            print("Incomplete first-half stats:",mid,len(first),"/5; retry next run")
            continue
        home=m.get("home_team") or {};away=m.get("away_team") or {}
        row={"match_id":mid,"fixture":str(home.get("name") or "Home")+" v "+str(away.get("name") or "Away"),
             "competition_id":cid(m),"kickoff_utc":ko.isoformat(),
             "observed_at":dt.datetime.now(dt.timezone.utc).isoformat(),
             "match_status":status,
             "half_time_score":score,"first_half_stats":first,"stats_payload":payload}
        db.table(TABLE).insert(row).execute()
        saved+=1
        print("Saved first-half stats:",mid,"fields:",len(first))
    print("HALFTIME FINISHED saved",saved,"calls",calls)

if __name__=="__main__":main()
