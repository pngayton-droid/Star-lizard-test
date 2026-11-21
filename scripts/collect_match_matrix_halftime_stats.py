"""Capture running live statistics only when TheStatsAPI confirms halftime.

The /stats endpoint is post-match only. /live-stats uses stats.<metric>.all.
This job runs on the existing five-minute workflow, sharing the kickoff cache.
"""
import os, json, datetime as dt
from pathlib import Path
import requests
from supabase import create_client

BASE="https://api.thestatsapi.com/api"
LEAGUES={"comp_3039","comp_8321","comp_8814","comp_5840","comp_4643","comp_0256","comp_3809","comp_8385","comp_8531","comp_6387"}
CACHE=Path(".cache/scanner_fixture_schedule.json")
TABLE="match_matrix_halftime_stats"
CAP=30
now=dt.datetime.now(dt.timezone.utc)
session=requests.Session()
session.headers["Authorization"]="Bearer "+os.environ["STATS_API_KEY"]
db=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])

def cid(m):
    comp=m.get("competition") or {}
    return str(m.get("competition_id") or (comp.get("id") if isinstance(comp,dict) else "") or "")

def get_json(path,params=None):
    response=session.get(BASE+path,params=params,timeout=25)
    if response.status_code in (404,409,429):
        print("Unavailable",path,response.status_code)
        return None,response.status_code
    response.raise_for_status()
    return response.json(),response.status_code

def main():
    if not CACHE.is_file():
        print("No fixture cache; skip without API calls")
        return
    cache=json.loads(CACHE.read_text())
    if cache.get("date")!=now.date().isoformat():
        print("Stale fixture cache; skip")
        return
    candidates={}
    for fixture in cache.get("matches") or []:
        if cid(fixture) not in LEAGUES:continue
        try:
            kickoff=dt.datetime.fromisoformat(str(fixture["utc_date"]).replace("Z","+00:00"))
            age=(now-kickoff).total_seconds()/60
        except (KeyError,TypeError,ValueError):continue
        # This is a broad *polling eligibility* window, NOT a halftime detector.
        if 40<=age<=75 and fixture.get("id"):
            candidates[str(fixture["id"])]=(fixture,kickoff)
    if not candidates:
        print("No plausible halftime candidates; zero API calls")
        return
    saved_ids=set()
    for mid in candidates:
        if db.table(TABLE).select("match_id").eq("match_id",mid).limit(1).execute().data:
            saved_ids.add(mid)
    pending=set(candidates)-saved_ids
    if not pending:
        print("All candidate first halves saved; zero API calls")
        return
    # One live fixture list request per scheduled run, not one status request per match.
    body,status=get_json("/football/matches",{"status":"live","per_page":100})
    calls=1
    if body is None:return
    live_rows=body.get("data") or []
    if not isinstance(live_rows,list):
        print("Unexpected live fixture list shape; skip")
        return
    count=0
    for item in live_rows:
        mid=str(item.get("id") or item.get("match_id") or "")
        if mid not in pending:continue
        live=item.get("live") or {}
        phase=str(live.get("match_status") or "").lower().replace("-","_")
        period=str(live.get("period") or "").lower().replace("-","_")
        if phase not in {"halftime","half_time"} and period not in {"halftime","half_time"}:
            continue
        if calls>=CAP:break
        response,status=get_json(f"/football/matches/{mid}/live-stats")
        calls+=1
        if response is None:
            if status==429:break
            continue
        payload=response.get("data") or {}
        meta=payload.get("meta") or {}
        meta_status=str(meta.get("match_status") or "").lower().replace("-","_")
        meta_period=str(meta.get("period") or "").lower().replace("-","_")
        if meta_status not in {"halftime","half_time"} and meta_period not in {"halftime","half_time"}:
            print("Live stats not confirmed halftime",mid,meta_status,meta_period)
            continue
        raw=payload.get("stats") or {}
        first={}
        for metric in ("expected_goals","total_shots","shots_on_target","corner_kicks","red_cards"):
            metric_data=raw.get(metric) or {}
            pair=metric_data.get("all") or {}
            if isinstance(pair,dict) and pair.get("home") is not None and pair.get("away") is not None:
                first[metric]={"home":pair["home"],"away":pair["away"]}
        # Do not store a snapshot without xG or the core first-half stats.
        required={"expected_goals","total_shots","shots_on_target","corner_kicks"}
        if not required.issubset(first):
            print("Missing required halftime stats",mid,sorted(required-set(first)))
            continue
        fixture,kickoff=candidates[mid]
        home=fixture.get("home_team") or {}
        away=fixture.get("away_team") or {}
        score=None
        current=item.get("score") or {}
        if current.get("home") is not None and current.get("away") is not None:
            score={"home":int(current["home"]),"away":int(current["away"])}
        if score is None:
            print("No confirmed halftime score",mid)
            continue
        row={"match_id":mid,
             "fixture":str(home.get("name") or "Home")+" v "+str(away.get("name") or "Away"),
             "competition_id":cid(fixture),"kickoff_utc":kickoff.isoformat(),
             "observed_at":dt.datetime.now(dt.timezone.utc).isoformat(),
             "match_status":"halftime","half_time_score":score,
             "first_half_stats":first,"stats_payload":payload}
        db.table(TABLE).upsert(row,on_conflict="match_id").execute()
        count+=1
        print("SAVED confirmed halftime",mid,"metrics",sorted(first))
    print("HALFTIME saved",count,"API calls",calls,"pending",len(pending))

if __name__=="__main__":main()
