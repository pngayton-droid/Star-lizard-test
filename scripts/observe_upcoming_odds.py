"""Record observed TheStatsAPI pre-match last_seen odds without overwriting prior observations.

Important: API 'last_seen' is not documented as a live timestamped quote.
The observation timestamp is OUR retrieval time, not the quote publication time.
"""
import os,time,requests
from datetime import datetime,timedelta,timezone
from supabase import create_client
BASE="https://api.thestatsapi.com/api"
KEY=os.environ["STATS_API_KEY"]
db=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])
session=requests.Session()
session.headers.update({"Authorization":"Bearer "+KEY})
def fetch(path,params=None):
 for attempt in range(3):
  response=session.get(BASE+path,params=params,timeout=25)
  if response.status_code==429:
   time.sleep(min(int(response.headers.get("Retry-After","30")),90));continue
  response.raise_for_status()
  return response.json()
 raise RuntimeError("API rate limit exhausted")
def parse_time(raw):
 if not raw:return None
 try:return datetime.fromisoformat(str(raw).replace("Z","+00:00")).astimezone(timezone.utc)
 except (ValueError,TypeError):return None
def number(x):
 try:
  value=float(x)
  return value if 1<value<1000 else None
 except (TypeError,ValueError):return None
now=datetime.now(timezone.utc)
days=[(now+timedelta(days=i)).date().isoformat() for i in range(3)]
fixtures=[]
for day in days:
 for page in range(1,8):
  payload=fetch("/football/matches",{"date_from":day,"date_to":day,"sort":"utc_date","per_page":100,"page":page})
  fixtures.extend(payload.get("data") or [])
  if page>=int((payload.get("meta") or {}).get("total_pages") or 1):break
seen=set();count=0;requests_made=0
for item in fixtures:
 mid=str(item.get("id") or item.get("match_id") or "")
 kick=parse_time(item.get("utc_date"))
 if not mid or not kick or mid in seen or not now<kick<=now+timedelta(hours=48):continue
 seen.add(mid)
 if requests_made>=90:break
 requests_made+=1
 try:
  payload=fetch("/football/matches/"+mid+"/odds")
  books=(payload.get("data") or {}).get("bookmakers") or []
  records=[]
  observed=datetime.now(timezone.utc).isoformat()
  for book in books:
   name=str(book.get("bookmaker") or "")
   if name.lower() not in ("bet365","pinnacle","betfair exchange","paddy power","betmgm uk"):continue
   market=(book.get("markets") or {}).get("match_odds") or {}
   prices=[number((market.get(side) or {}).get("last_seen")) for side in ("home","draw","away")]
   if not all(prices):continue
   records.append({"match_id":mid,"kickoff_utc":kick.isoformat(),"competition_id":str(item.get("competition_id") or ""),"bookmaker":name,"observed_at":observed,"home_odds":prices[0],"draw_odds":prices[1],"away_odds":prices[2],"quote_field":"last_seen"})
  if records:
   db.table("odds_observation_snapshots").insert(records).execute()
   count+=len(records)
 except Exception as exc:
  print("FAILED",mid,str(exc)[:180],flush=True)
 time.sleep(1.2)
print("SNAPSHOT_SUMMARY fixtures",len(seen),"requests",requests_made,"observations",count,flush=True)
