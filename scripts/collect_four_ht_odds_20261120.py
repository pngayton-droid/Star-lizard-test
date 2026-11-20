"""One-night, four-fixture HT live odds trial. Never touches historical model tables."""
import os,datetime as dt,requests
from supabase import create_client
DAY=dt.date(2026,11,20)
FIXTURES=[
 ("comp_4643","Bayern Munich","Cologne",19,30,("bayern","köln","koln","cologne")),
 ("comp_0256","Troyes","Le Havre",19,45,("troyes","havre")),
 ("comp_8531","Cercle Brugge","Westerlo",19,45,("cercle","westerlo")),
 ("comp_8814","Athletic Bilbao","Espanyol",20,0,("athletic","espanyol")),
]
API="https://api.thestatsapi.com/api"
session=requests.Session();session.headers["Authorization"]="Bearer "+os.environ["STATS_API_KEY"]
db=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])
calls=0;quota=None
def fetch(path,params=None):
 global calls,quota
 if calls>=12:raise RuntimeError("12-request run cap")
 r=session.get(API+path,params=params,timeout=25);calls+=1
 v=r.headers.get("X-Monthly-Quota-Remaining")
 if v is not None:
  try:quota=int(v)
  except ValueError:pass
 if quota is not None and quota<=int(os.getenv("HT_ODDS_RESERVE","500")):raise RuntimeError("Monthly quota reserve reached")
 if r.status_code in (404,409,429):
  print("HTTP",r.status_code,path);return None
 r.raise_for_status();return r.json().get("data")
def main():
 now=dt.datetime.now(dt.timezone.utc)
 if now.date()!=DAY:print("Outside one-night trial");return
 for cid,home,away,hh,mm,keywords in FIXTURES:
  kickoff=dt.datetime(2026,11,20,hh,mm,tzinfo=dt.timezone.utc)
  delta=(now-kickoff).total_seconds()/60
  if not (38<=delta<=70):continue
  data=fetch("/football/matches",{"competition_id":cid,"date_from":str(DAY),"date_to":str(DAY),"per_page":100})
  if not isinstance(data,list):continue
  matches=[m for m in data if any(x in str((m.get("home_team") or {}).get("name","")).lower() for x in keywords[:1]) and any(x in str((m.get("away_team") or {}).get("name","")).lower() for x in keywords[1:])]
  if len(matches)!=1:
   print("Fixture not uniquely identified",home,away,len(matches));continue
  match=matches[0];mid=match.get("id")
  if not mid or not match.get("live_odds_available"):
   print("No live odds flag",home,away,mid);continue
  live=fetch("/football/matches/"+mid+"/odds/live")
  if not isinstance(live,dict):continue
  # Save the bookmaker's raw quoted markets, never fabricate an HT-specific market.
  meta=fetch("/football/matches/"+mid+"/live-stats") or {}
  m=meta.get("meta") or {};status=m.get("match_status")
  minute=m.get("elapsed_minutes")
  rows=[]
  for book in live.get("bookmakers") or []:
   name=book.get("bookmaker");markets=book.get("markets")
   if not name or not isinstance(markets,dict):continue
   rows.append({"match_id":mid,"fixture":home+" v "+away,"competition_id":cid,
    "observed_at":dt.datetime.now(dt.timezone.utc).isoformat(),
    "match_status":str(status) if status is not None else None,
    "elapsed_minutes":minute if isinstance(minute,int) else None,
    "bookmaker":name,"markets":markets,
    "snapshot_kind":"halftime" if str(status).lower() in ("halftime","half_time","ht","half-time") else "near_halftime"})
  if rows:db.table("ht_odds_trial_20261120").insert(rows).execute()
  print(home,"v",away,"saved",len(rows),"books",status,minute,"requests",calls)
 print("DONE",calls,"requests; quota remaining",quota)
if __name__=="__main__":main()
