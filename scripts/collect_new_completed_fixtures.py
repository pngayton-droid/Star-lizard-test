"""Low-quota incremental collection of completed matches in ten leagues.
Does not retrain or change the frozen fair-odds model.
"""
import os,time,datetime as dt,requests
from supabase import create_client

LEAGUES={"Premier League":"comp_3039","Championship":"comp_8321","La Liga":"comp_8814","Serie A":"comp_5840","Bundesliga":"comp_4643","Ligue 1":"comp_0256","Eredivisie":"comp_3809","Primeira Liga":"comp_8385","Belgian Pro League":"comp_8531","Scottish Premiership":"comp_6387"}
DB=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])
S=requests.Session();S.headers["Authorization"]="Bearer "+os.environ["STATS_API_KEY"]
CAP=int(os.getenv("COLLECTOR_REQUEST_CAP","120"));RESERVE=int(os.getenv("COLLECTOR_QUOTA_RESERVE","500"))
BASE="https://api.thestatsapi.com/api";calls=0;remaining=None
def get(path,params=None):
 global calls,remaining
 for attempt in range(3):
  if calls>=CAP:raise RuntimeError("Daily API cap reached")
  r=S.get(BASE+path,params=params,timeout=35);calls+=1
  q=r.headers.get("X-Monthly-Quota-Remaining")
  if q is not None:
   try:remaining=int(q)
   except ValueError:pass
  if remaining is not None and remaining<=RESERVE:raise RuntimeError("Quota reserve reached")
  if r.status_code==429:
   time.sleep(min(int(r.headers.get("Retry-After","30")),90));continue
  if r.status_code==404:return None
  r.raise_for_status();return r.json().get("data")
 raise RuntimeError("Rate-limit retries exhausted")
def existing(table,cols):
 rows=[];offset=0
 while True:
  part=DB.table(table).select(cols).range(offset,offset+999).execute().data or []
  rows.extend(part)
  if len(part)<1000:break
  offset+=1000
 return rows
def score(m,period):
 # Score shapes vary by endpoint; reject ambiguous rather than fabricate results.
 for root in [m.get("score"),m.get("scores")]:
  if not isinstance(root,dict):continue
  v=root.get(period)
  if isinstance(v,dict) and v.get("home") is not None and v.get("away") is not None:
   return int(v["home"]),int(v["away"])
 return None
def main():
 today=dt.datetime.now(dt.timezone.utc).date()
 # Initial backfill starts after the verified Nov 8 cutoff; subsequent runs recheck
 # the last seven days for late-arriving statistics without scanning all history.
 latest=DB.table("historical_xg").select("match_date").gt("match_date","2026-11-08").order("match_date",desc=True).limit(1).execute().data or []
 start=dt.date(2026,11,9)
 if latest:start=max(start,dt.date.fromisoformat(latest[0]["match_date"])-dt.timedelta(days=7))
 end=today-dt.timedelta(days=1)
 if start>end:print("No completed dates to scan");return
 x={r["match_id"]:r for r in existing("historical_xg","match_id,home_ht_xg,away_ht_xg")}
 e={r["match_id"]:r for r in existing("historical_match_events","match_id,stats_status,timeline_status")}
 counts={"listed":0,"already_complete":0,"new":0,"updated":0,"missing":0}
 print(f"Scanning {start} to {end}; maximum {CAP} API calls; reserve {RESERVE}")
 for league,cid in LEAGUES.items():
  page=1
  while True:
   if calls>=CAP-2:print("Request cap nearly reached; stop safely");return
   data=get("/football/matches",{"competition_id":cid,"status":"finished","date_from":str(start),"date_to":str(end),"per_page":100,"page":page,"sort":"-utc_date"})
   if not isinstance(data,list):raise RuntimeError("Unexpected fixtures response")
   if not data:break
   for m in data:
    mid=str(m.get("id") or m.get("match_id") or "")
    if not mid:continue
    counts["listed"]+=1
    old=x.get(mid) or {};old_ev=e.get(mid) or {}
    have_xg=old.get("home_ht_xg") is not None and old.get("away_ht_xg") is not None
    have_events=old_ev.get("stats_status")==200 and old_ev.get("timeline_status")==200
    if have_xg and have_events:counts["already_complete"]+=1;continue
    if calls>=CAP-2:
     print("Daily request cap; remaining fixtures next run",counts,"calls",calls);return
    stats=None;timeline=None
    if not have_xg or old_ev.get("stats_status")!=200:
     stats=get(f"/football/matches/{mid}/stats")
    if old_ev.get("timeline_status")!=200:
     timeline=get(f"/football/matches/{mid}/timeline")
    if stats is not None or timeline is not None:
     patch={"match_id":mid}
     if stats is not None:patch.update(stats_data=stats,stats_status=200)
     if timeline is not None:patch.update(timeline_data=timeline,timeline_status=200)
     DB.table("historical_match_events").upsert(patch,on_conflict="match_id").execute()
    if stats is None and not have_xg:counts["missing"]+=1;continue
    if not have_xg:
     overview=(stats or {}).get("overview") or {}
     expected=overview.get("expected_goals") or {}
     full=expected.get("all") or {};half=expected.get("first_half") or {}
     vals=[full.get("home"),full.get("away"),half.get("home"),half.get("away")]
     if any(v is None for v in vals):counts["missing"]+=1;continue
     home=m.get("home_team") or {};away=m.get("away_team") or {}
     date=str(m.get("utc_date") or m.get("date") or "")[:10]
     if not date or not home.get("name") or not away.get("name"):counts["missing"]+=1;continue
     row={"match_id":mid,"match_date":date,"home_team":home["name"],"away_team":away["name"],"competition_id":cid,
          "home_xg":vals[0],"away_xg":vals[1],"home_ht_xg":vals[2],"away_ht_xg":vals[3]}
     final=score(m,"full_time") or score(m,"fullTime")
     ht=score(m,"half_time") or score(m,"halfTime")
     if final and ht and all(a>=b for a,b in zip(final,ht)):
      row.update(home_goals=final[0],away_goals=final[1],home_ht_goals=ht[0],away_ht_goals=ht[1])
     DB.table("historical_xg").upsert(row,on_conflict="match_id").execute()
     if final and ht:
      diff=(final[0]-ht[0],final[1]-ht[1])
      trailing="home" if ht[0]<ht[1] else "away" if ht[1]<ht[0] else None
      outcome={"competition_id":cid,"match_date":date,"home_team":home["name"],"away_team":away["name"],
               "home_ht_goals":ht[0],"away_ht_goals":ht[1],"home_ht_xg":vals[2],"away_ht_xg":vals[3],
               "home_goals":final[0],"away_goals":final[1],"home_second_half_goals":diff[0],"away_second_half_goals":diff[1],
               "trailing_side":trailing,"trailing_ht_xg":vals[2] if trailing=="home" else vals[3] if trailing=="away" else None}
      present=(DB.table("halftime_research_outcomes").select("match_date")
       .eq("match_date",date).eq("home_team",home["name"]).eq("away_team",away["name"]).limit(1).execute().data)
      if not present:DB.table("halftime_research_outcomes").insert(outcome).execute()
     counts["updated" if mid in x else "new"]+=1
   if len(data)<100:break
   page+=1
  print(league,"done; calls",calls,flush=True)
 print("FINISHED",counts,"API calls",calls,"quota remaining",remaining)
if __name__=="__main__":main()
