"""Resumable full historical collector; league matches only; never overwrite complete records."""
import os,time,requests
from datetime import datetime,timezone
from supabase import create_client
BASE="https://api.thestatsapi.com/api"
S=requests.Session();S.headers["Authorization"]="Bearer "+os.environ["STATS_API_KEY"]
DB=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])
LEAGUES=[("Premier League","comp_3039"),("Championship","comp_8321"),("La Liga","comp_8814"),("Serie A","comp_5840"),("Bundesliga","comp_4643"),("Ligue 1","comp_0256"),("Eredivisie","comp_3809"),("Primeira Liga","comp_8385"),("Belgian Pro League","comp_8531"),("Scottish Premiership","comp_6387")]
NAME="complete_historical_v5"
LIMIT=int(os.getenv("RUN_REQUEST_LIMIT","5500"))
MIN_REMAINING=int(os.getenv("MIN_REMAINING","350"))
calls=0;remaining=None;last=0
def api(path,params=None):
 global calls,remaining,last
 for attempt in range(4):
  if calls>=LIMIT or (remaining is not None and remaining<=MIN_REMAINING): return None,0
  delay=2.1-(time.monotonic()-last)
  if delay>0:time.sleep(delay)
  last=time.monotonic()
  try:r=S.get(BASE+path,params=params,timeout=40)
  except requests.RequestException as exc:
   print("NETWORK",str(exc)[:160],flush=True);time.sleep(10);continue
  calls+=1
  quota=r.headers.get("X-Monthly-Quota-Remaining")
  if quota and quota.isdigit():remaining=int(quota)
  if r.status_code==429:
   time.sleep(min(180,max(10,int(r.headers.get("Retry-After","60")))));continue
  if r.status_code in (404,204):return None,r.status_code
  if r.status_code==400:
   try:
    if (r.json().get("error") or {}).get("code")=="PAGE_OUT_OF_RANGE":return {"data":[]},200
   except ValueError:pass
  r.raise_for_status()
  return r.json(),r.status_code
 raise RuntimeError("API retries exhausted")
def rows(table,fields):
 out=[];offset=0
 while True:
  part=DB.table(table).select(fields).range(offset,offset+999).execute().data or []
  out+=part
  if len(part)<1000:return out
  offset+=1000
def progress():
 r=DB.table("collector_progress").select("*").eq("collector_name",NAME).limit(1).execute().data
 return (int(r[0]["season"]),int(r[0]["league_index"]),int(r[0]["page"]),int(r[0]["match_index"])) if r else (2021,0,1,0)
def save(s,l,p,m):
 DB.table("collector_progress").upsert({"collector_name":NAME,"season":s,"league_index":l,"page":p,"match_index":m},on_conflict="collector_name").execute()
def upsert(table,row):
 # PATCH existing rows to preserve fields not present in the update.
 match_id=row["match_id"]
 found=DB.table(table).select("match_id").eq("match_id",match_id).limit(1).execute().data
 if found:
  DB.table(table).update({k:v for k,v in row.items() if k!="match_id"}).eq("match_id",match_id).execute()
 else:
  DB.table(table).insert(row).execute()
def collect(mid,match,comp,existing,stats_set,timeline_set,odds_set):
 now=datetime.now(timezone.utc).isoformat()
 # Save the fixture independently of xG availability. Historical xG can be null.
 if mid not in existing:
  home=match.get("home_team") or {};away=match.get("away_team") or {}
  date=str(match.get("utc_date") or match.get("date") or "")[:10]
  if not date or not home.get("name") or not away.get("name"):
   print("SKIP_INCOMPLETE_FIXTURE",mid,flush=True)
   return True
  upsert("historical_xg",{"match_id":mid,"match_date":date,"home_team":home["name"],"away_team":away["name"],"competition_id":comp})
  existing.add(mid)
  print("SAVED_FIXTURE",mid,date,flush=True)
 if mid not in stats_set:
  payload,status=api(f"/football/matches/{mid}/stats")
  if status==0:return False
  if payload and isinstance(payload.get("data"),dict) and payload["data"]:
   stats=payload["data"]
   upsert("historical_match_events",{"match_id":mid,"stats_data":stats,"stats_status":status,"collected_at":now})
   stats_set.add(mid)
   overview=(stats.get("overview") or {}).get("expected_goals") or {}
   full=overview.get("all") or {};half=overview.get("first_half") or {}
   xg={"home_xg":full.get("home"),"away_xg":full.get("away"),"home_ht_xg":half.get("home"),"away_ht_xg":half.get("away")}
   if any(v is not None for v in xg.values()):
    DB.table("historical_xg").update({k:v for k,v in xg.items() if v is not None}).eq("match_id",mid).execute()
   print("STATS",mid,"xg_fields",sum(v is not None for v in xg.values()),flush=True)
  else:print("STATS_UNAVAILABLE",mid,status,flush=True)
 if mid not in timeline_set:
  payload,status=api(f"/football/matches/{mid}/timeline")
  if status==0:return False
  if payload and isinstance(payload.get("data"),dict) and payload["data"]:
   upsert("historical_match_events",{"match_id":mid,"timeline_data":payload["data"],"timeline_status":status,"collected_at":now})
   timeline_set.add(mid)
   print("TIMELINE",mid,flush=True)
 if mid not in odds_set:
  payload,status=api(f"/football/matches/{mid}/odds")
  if status==0:return False
  if payload and isinstance(payload.get("data"),dict) and payload["data"]:
   books=payload["data"].get("bookmakers") or []
   upsert("historical_match_odds",{"match_id":mid,"odds_payload":payload,"fetch_status":"collected","bookmaker_names":[str(b.get("bookmaker")) for b in books if b.get("bookmaker")],"fetched_at":now})
   odds_set.add(mid)
   print("ODDS",mid,"bookmakers",len(books),flush=True)
 return True

def main():
 existing={r["match_id"] for r in rows("historical_xg","match_id") if r.get("match_id")}
 ev=rows("historical_match_events","match_id,stats_data,timeline_data")
 stats_set={r["match_id"] for r in ev if r.get("stats_data") is not None}
 timeline_set={r["match_id"] for r in ev if r.get("timeline_data") is not None}
 odds_set={r["match_id"] for r in rows("historical_match_odds","match_id,odds_payload") if r.get("odds_payload") is not None}
 print("START",len(existing),"stats",len(stats_set),"timelines",len(timeline_set),"odds",len(odds_set),flush=True)
 print("REPAIRS DEFERRED; PRIORITIZING MISSING HISTORICAL SEASONS",flush=True)
 season,li,page,idx=progress()
 if season>2021:raise RuntimeError(f"Refusing to scan already collected season {season}")
 print("STARTING HISTORICAL SEASON",season,"league",LEAGUES[li][0],flush=True)
 while season>=2016:
  if calls>=LIMIT-4 or (remaining is not None and remaining<=MIN_REMAINING):break
  league,comp=LEAGUES[li]
  payload,status=api("/football/matches",{"competition_id":comp,"status":"finished","date_from":f"{season}-08-01","date_to":f"{season+1}-07-31","per_page":20,"page":page,"sort":"-utc_date"})
  if status==0:break
  matches=(payload or {}).get("data") or []
  if not isinstance(matches,list):raise RuntimeError("Unexpected match list")
  if not matches:
   li+=1
   if li==len(LEAGUES):li=0;season-=1
   page=1;idx=0;save(season,li,page,idx);continue
  print("PAGE",season,league,page,len(matches),"calls",calls,"remaining",remaining,flush=True)
  while idx<len(matches):
   if calls>=LIMIT-4 or (remaining is not None and remaining<=MIN_REMAINING):break
   match=matches[idx];mid=str(match.get("id") or match.get("match_id") or "")
   if mid and not (mid in existing and mid in stats_set and mid in timeline_set and mid in odds_set):
    if not collect(mid,match,comp,existing,stats_set,timeline_set,odds_set):break
   idx+=1;save(season,li,page,idx)
  if idx<len(matches):break
  page+=1;idx=0;save(season,li,page,idx)
 print("STOP","calls",calls,"remaining",remaining,"position",season,li,page,idx,"matches",len(existing),flush=True)
if __name__=="__main__":main()
