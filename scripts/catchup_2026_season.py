"""One-time bounded 2026/27 completed-fixture catch-up. Scores first; missing stats second."""
import os,time,requests
from datetime import date,timedelta,datetime,timezone
from supabase import create_client
BASE="https://api.thestatsapi.com/api"
LEAGUES=["comp_3039","comp_8321","comp_8814","comp_5840","comp_4643","comp_0256","comp_3809","comp_8385","comp_8531","comp_6387"]
LIMIT=min(8000,int(os.getenv("CATCHUP_MAX_REQUESTS","8000")))
MIN_REMAINING=int(os.getenv("CATCHUP_MIN_REMAINING","400"))
db=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])
session=requests.Session();session.headers["Authorization"]="Bearer "+os.environ["STATS_API_KEY"]
calls=0;remaining=None;last=0
def api(path,params=None):
 global calls,remaining,last
 for attempt in range(3):
  if calls>=LIMIT or (remaining is not None and remaining<=MIN_REMAINING):
   raise RuntimeError("STOP: request or remaining-quota safety threshold reached")
  delay=1.15-(time.monotonic()-last)
  if delay>0:time.sleep(delay)
  last=time.monotonic()
  try:r=session.get(BASE+path,params=params,timeout=35)
  except requests.RequestException as e:
   print("NETWORK",str(e)[:100],flush=True);time.sleep(5);continue
  calls+=1
  q=r.headers.get("X-Monthly-Quota-Remaining")
  if q and q.isdigit():remaining=int(q)
  if r.status_code==429:
   time.sleep(min(90,max(5,int(r.headers.get("Retry-After","30")))));continue
  if r.status_code==404:return {}
  r.raise_for_status()
  return r.json()
 raise RuntimeError("API retry failure")
def score_fields(match):
 score=match.get("score") or {}
 reg=score.get("regulation") or {}
 return {"home_goals":reg.get("home"),"away_goals":reg.get("away"),"home_ht_goals":score.get("half_time_home"),"away_ht_goals":score.get("half_time_away")}
def run():
 existing={}
 offset=0
 while True:
  rows=db.table("historical_xg").select("match_id,home_goals,away_goals,home_ht_goals,away_ht_goals,home_xg,away_xg,home_ht_xg,away_ht_xg").range(offset,offset+999).execute().data or []
  for row in rows:existing[str(row["match_id"])]=row
  if len(rows)<1000:break
  offset+=1000
 start=date(2026,8,1);end=datetime.now(timezone.utc).date()-timedelta(days=1)
 added=0;repaired=0;enriched=0;seen=set()
 for comp in LEAGUES:
  day=start
  while day<=end:
   if calls>=LIMIT-15 or (remaining is not None and remaining<=MIN_REMAINING):raise RuntimeError("Safety stop")
   payload=api("/football/matches",{"competition_id":comp,"status":"finished","date_from":day.isoformat(),"date_to":day.isoformat(),"per_page":100,"page":1})
   matches=payload.get("data") or []
   if isinstance(matches,dict):matches=matches.get("matches") or matches.get("items") or []
   if not isinstance(matches,list):raise RuntimeError("Unexpected fixture response")
   for match in matches:
    mid=str(match.get("id") or match.get("match_id") or "")
    if not mid or mid in seen:continue
    seen.add(mid)
    home=(match.get("home_team") or {}).get("name");away=(match.get("away_team") or {}).get("name")
    match_day=str(match.get("utc_date") or match.get("date") or "")[:10]
    if not home or not away or not match_day:continue
    prior=existing.get(mid) or {}
    scores=score_fields(match)
    if scores["home_goals"] is None or scores["away_goals"] is None:
     detail=(api("/football/matches/"+mid).get("data") or {})
     scores=score_fields(detail)
    if scores["home_goals"] is None or scores["away_goals"] is None:
     print("NO_FINAL_SCORE",mid,flush=True);continue
    row={"match_id":mid,"match_date":match_day,"competition_id":comp,"home_team":home,"away_team":away}
    row.update({k:v for k,v in scores.items() if v is not None and prior.get(k) is None})
    if not prior:
     db.table("historical_xg").insert(row).execute();added+=1
    else:
     updates={k:v for k,v in row.items() if k!="match_id" and (k in ("home_goals","away_goals","home_ht_goals","away_ht_goals") and prior.get(k) is None)}
     if updates:db.table("historical_xg").update(updates).eq("match_id",mid).execute();repaired+=1
    if any(prior.get(k) is None for k in ("home_xg","away_xg","home_ht_xg","away_ht_xg")):
     stats=(api("/football/matches/"+mid+"/stats").get("data") or {})
     if isinstance(stats,dict) and stats:
      db.table("historical_match_events").upsert({"match_id":mid,"stats_data":stats,"stats_status":200,"collected_at":datetime.now(timezone.utc).isoformat()},on_conflict="match_id").execute()
      expected=((stats.get("overview") or {}).get("expected_goals") or {})
      full=expected.get("all") or {};half=expected.get("first_half") or {}
      xg=dict(home_xg=full.get("home"),away_xg=full.get("away"),home_ht_xg=half.get("home"),away_ht_xg=half.get("away"))
      updates={k:v for k,v in xg.items() if v is not None and prior.get(k) is None}
      if updates:db.table("historical_xg").update(updates).eq("match_id",mid).execute();enriched+=1
   day+=timedelta(days=1)
  print("LEAGUE_DONE",comp,"seen",len(seen),"added",added,"repaired",repaired,"enriched",enriched,"calls",calls,"remaining",remaining,flush=True)
 print("COMPLETE","added",added,"repaired",repaired,"enriched",enriched,"calls",calls,"remaining",remaining,flush=True)
if __name__=="__main__":run()
