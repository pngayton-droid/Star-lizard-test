"""Fast halftime poller: run for up to 13 minutes, polling every 45 seconds.

Uses the shared daily kickoff cache. Saves only confirmed stable halftime stats.
The prematch odds collector remains independent.
"""
import os, json, time, datetime as dt
from pathlib import Path
import requests
from supabase import create_client

BASE="https://api.thestatsapi.com/api"
LEAGUES={"comp_3039","comp_8321","comp_8814","comp_5840","comp_4643","comp_0256","comp_3809","comp_8385","comp_8531","comp_6387"}
CACHE=Path(".cache/scanner_fixture_schedule.json")
TABLE="match_matrix_halftime_stats"
POLL_SECONDS=45
DURATION_SECONDS=int(os.getenv("HT_POLL_DURATION","780"))
CAP=int(os.getenv("HT_REQUEST_CAP","45"))
RESERVE=int(os.getenv("HT_QUOTA_RESERVE","500"))
session=requests.Session()
session.headers["Authorization"]="Bearer "+os.environ["STATS_API_KEY"]
db=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])
calls=0
remaining=None
stopped=False

def utcnow():return dt.datetime.now(dt.timezone.utc)
def parse_time(value):
    try:return dt.datetime.fromisoformat(str(value).replace("Z","+00:00"))
    except (ValueError,TypeError):return None
def cid(m):
    c=m.get("competition") or {}
    return str(m.get("competition_id") or (c.get("id") if isinstance(c,dict) else "") or "")
def phase(row):
    live=row.get("live") or {}
    return str(live.get("match_status") or "").lower().replace("-","_"),str(live.get("period") or "").lower().replace("-","_")
def is_ht(row):
    status,period=phase(row)
    return status in ("halftime","half_time") or period in ("halftime","half_time")
def score(row):
    s=row.get("score") or {}
    try:
        if s.get("home") is not None and s.get("away") is not None:
            return {"home":int(s["home"]),"away":int(s["away"])}
    except (ValueError,TypeError):pass
    return None

def get(path,params=None):
    global calls,remaining,stopped
    if calls>=CAP or stopped:return None
    r=session.get(BASE+path,params=params,timeout=20)
    calls+=1
    q=r.headers.get("X-Monthly-Quota-Remaining")
    if q is not None:
        try:remaining=int(q)
        except ValueError:pass
    if remaining is not None and remaining<=RESERVE:
        print("STOP quota reserve reached",remaining,flush=True)
        stopped=True
        return None
    if r.status_code==429:
        print("STOP HTTP 429 retry-after",r.headers.get("Retry-After"),flush=True)
        stopped=True
        return None
    if r.status_code in (404,409):
        print("Unavailable",path,r.status_code,flush=True)
        return None
    r.raise_for_status()
    return r.json()

def live_list():
    body=get("/football/matches",{"status":"live","per_page":100})
    if not body:return {}
    rows=body.get("data") or []
    if not isinstance(rows,list):return {}
    pages=int((body.get("meta") or {}).get("total_pages") or 1)
    if pages>1:
        print("WARNING live fixtures paginated",pages,flush=True)
        for page in range(2,min(pages,3)+1):
            next_page=get("/football/matches",{"status":"live","per_page":100,"page":page})
            if not next_page:break
            rows.extend(next_page.get("data") or [])
    return {str(m.get("id") or m.get("match_id") or ""):m for m in rows if isinstance(m,dict)}

def stats_snapshot(mid):
    body=get("/football/matches/"+mid+"/live-stats")
    if not body:return None
    payload=body.get("data") or {}
    meta=payload.get("meta") or {}
    status=str(meta.get("match_status") or "").lower().replace("-","_")
    period=str(meta.get("period") or "").lower().replace("-","_")
    if status not in ("halftime","half_time") and period not in ("halftime","half_time"):
        print("REJECT live-stats not halftime",mid,status,period,flush=True)
        return None
    raw=payload.get("stats") or {}
    first={}
    for metric in ("expected_goals","total_shots","shots_on_target","corner_kicks","red_cards"):
        values=(raw.get(metric) or {}).get("all") or {}
        if isinstance(values,dict) and values.get("home") is not None and values.get("away") is not None:
            first[metric]={"home":values["home"],"away":values["away"]}
    return {"payload":payload,"meta":meta,"first":first,"observed":utcnow()}

def collect_ht_odds(mid, fixture, kickoff, first_seen):
    """One bounded odds probe at verified halftime; never assert live-price freshness."""
    existing=(db.table("match_matrix_halftime_odds").select("bookmaker")
              .eq("match_id",mid).limit(1).execute().data or [])
    if existing:
        return
    payload=get("/football/matches/"+mid+"/odds/live",
                {"bookmaker":"bet365,pinnacle,betfair-sportsbook"})
    data=(payload or {}).get("data") or {}
    books=data.get("bookmakers") or []
    if not books:
        print("HT_ODDS_UNAVAILABLE",mid,flush=True)
        return
    home=(fixture.get("home_team") or {}).get("name") or "Home"
    away=(fixture.get("away_team") or {}).get("name") or "Away"
    saved=0
    for book in books:
        if not isinstance(book,dict):continue
        name=book.get("bookmaker")
        markets=book.get("markets")
        if not name or not isinstance(markets,dict) or not markets:continue
        record={"match_id":mid,"bookmaker":str(name),"observed_at":utcnow().isoformat(),
                "fixture":home+" v "+away,"kickoff_utc":kickoff.isoformat(),
                "ht_first_seen_at":first_seen.isoformat(),
                "status_at_request":"halftime_verified_by_two_stats_snapshots",
                "markets":markets,"provenance":"live_odds_endpoint"}
        db.table("match_matrix_halftime_odds").upsert(
            record,on_conflict="match_id,bookmaker",ignore_duplicates=True).execute()
        saved+=1
    print("HT_ODDS_PROBE",mid,"bookmakers",saved,
          "source dedicated live odds endpoint; inspect actual returned price fields",flush=True)

def main():
    if not CACHE.exists():
        print("No daily kickoff cache; no API calls",flush=True)
        return
    cached=json.loads(CACHE.read_text())
    if cached.get("date")!=utcnow().date().isoformat():
        print("Stale kickoff cache; no API calls",flush=True)
        return
    matches={}
    for m in cached.get("matches") or []:
        if cid(m) not in LEAGUES:continue
        ko=parse_time(m.get("utc_date"))
        if ko and m.get("id"):
            matches[str(m["id"])]=(m,ko)
    start=utcnow()
    end=time.monotonic()+DURATION_SECONDS
    # Do not hold a runner open unless at least one first-half window overlaps this run.
    def possible(mid,at):
        age=(at-matches[mid][1]).total_seconds()/60
        return 30<=age<=75
    if not any(30<=((start-m[1]).total_seconds()/60)<=75 or
               30<=((start+dt.timedelta(seconds=DURATION_SECONDS)-m[1]).total_seconds()/60)<=75 or
               start<=m[1]+dt.timedelta(minutes=45)<=start+dt.timedelta(seconds=DURATION_SECONDS)
               for m in matches.values()):
        print("No halftime window during this run; zero API calls",flush=True)
        return
    captured={str(row["match_id"]) for row in (db.table(TABLE).select("match_id")
             .gte("kickoff_utc",start.date().isoformat()).execute().data or [])}
    first_seen={}
    pending={}
    phase_seen={}
    print("START halftime loop",start.isoformat(),"matches",len(matches),"already_saved",len(captured),flush=True)
    while time.monotonic()<end and not stopped and calls<CAP:
        cycle=utcnow()
        eligible={mid for mid in matches if possible(mid,cycle)}
        if not eligible:
            # Do not stop prematurely: later kickoffs may enter the window.
            time.sleep(min(POLL_SECONDS,max(0,end-time.monotonic())))
            continue
        live=live_list()
        for mid in eligible:
            row=live.get(mid)
            if row:
                status,period=phase(row)
                state="halftime" if is_ht(row) else ("second_half" if period in ("second_half","2nd_half","2h","2","second") else (status or period or "unknown"))
                if phase_seen.get(mid)!=state:
                    phase_seen[mid]=state
                    stamp=utcnow()
                    fixture,ko=matches[mid]
                    names=[(fixture.get(k) or {}).get("name") or fallback for k,fallback in (("home_team","Home"),("away_team","Away"))]
                    current_score=score(row) or {}
                    live_meta=row.get("live") or {}
                    elapsed=live_meta.get("elapsed_minutes")
                    try:elapsed=int(elapsed) if elapsed is not None else None
                    except (TypeError,ValueError):elapsed=None
                    log={"match_id":mid,"observed_at":stamp.isoformat(),
                         "kickoff_utc":ko.isoformat(),"fixture":" v ".join(names),
                         "match_status":status,"period":period,"elapsed_minutes":elapsed,
                         "api_updated_at":str(live_meta.get("updated_at") or ""),
                         "home_score":current_score.get("home"),"away_score":current_score.get("away")}
                    db.table("match_matrix_live_phase_log").insert(log).execute()
                    print("PHASE_TRANSITION",mid,state,stamp.isoformat(),
                          "api_updated_at",log["api_updated_at"],
                          "elapsed",elapsed,flush=True)
            if mid in captured:
                continue
            if not row or not is_ht(row):
                pending.pop(mid,None)
                continue
            if mid not in first_seen:
                first_seen[mid]=utcnow()
                print("HT_FIRST_SEEN",mid,first_seen[mid].isoformat(),
                      "live_updated_at",(row.get("live") or {}).get("updated_at"),flush=True)
            if mid not in pending:
                # Allow provider's 30-second live-stats cache to refresh.
                if (utcnow()-first_seen[mid]).total_seconds()<35:continue
                s=stats_snapshot(mid)
                if s:pending[mid]=(s,score(row))
                continue
            s1,score1=pending[mid]
            if (utcnow()-s1["observed"]).total_seconds()<35:continue
            s2=stats_snapshot(mid)
            if not s2:continue
            score2=score(row)
            required={"expected_goals","total_shots","shots_on_target","corner_kicks"}
            if not required.issubset(s2["first"]):
                print("NO_XG_OR_CORE_STATS",mid,sorted(required-set(s2["first"])),flush=True)
                pending[mid]=(s2,score2)
                continue
            if s1["first"]!=s2["first"] or score1!=score2 or score2 is None:
                print("UNSTABLE_STATS_OR_SCORE",mid,flush=True)
                pending[mid]=(s2,score2)
                continue
            # Live-list status was refreshed at the start of this cycle, and
            # both stats calls reported halftime. No claim of whistle-time accuracy.
            fixture,ko=matches[mid]
            h=fixture.get("home_team") or {}
            a=fixture.get("away_team") or {}
            meta=s2["meta"]
            elapsed=(row.get("live") or {}).get("elapsed_minutes")
            try:elapsed=int(elapsed) if elapsed is not None else None
            except (ValueError,TypeError):elapsed=None
            record={"match_id":mid,
              "fixture":str(h.get("name") or "Home")+" v "+str(a.get("name") or "Away"),
              "competition_id":cid(fixture),"kickoff_utc":ko.isoformat(),
              "observed_at":s2["observed"].isoformat(),"match_status":"halftime",
              "half_time_score":score2,"first_half_stats":s2["first"],
              "stats_payload":s2["payload"],"quality":"stable_two_snapshots",
              "ht_first_seen_at":first_seen[mid].isoformat(),
              "second_observed_at":s2["observed"].isoformat(),
              "api_updated_at":str((row.get("live") or {}).get("updated_at") or ""),
              "elapsed_minutes":elapsed,"raw_meta":meta}
            # Never overwrite an earlier saved record.
            db.table(TABLE).upsert(record,on_conflict="match_id",ignore_duplicates=True).execute()
            captured.add(mid)
            pending.pop(mid,None)
            collect_ht_odds(mid,fixture,ko,first_seen[mid])
            print("HT_SAVED",mid,"kickoff",ko.isoformat(),
                  "first_seen",first_seen[mid].isoformat(),
                  "captured",s2["observed"].isoformat(),
                  "minutes_after_ko",round((s2["observed"]-ko).total_seconds()/60,1),flush=True)
        time.sleep(min(POLL_SECONDS,max(0,end-time.monotonic())))
    print("FINISH API calls",calls,"remaining",remaining,"captured",len(captured),flush=True)

if __name__=="__main__":main()
