"""Small read-only TheStatsAPI availability probe. No Supabase writes."""
import os, json, time, requests
from datetime import datetime, timezone
BASE="https://api.thestatsapi.com/api"
KEY=os.environ["STATS_API_KEY"]
S=requests.Session();S.headers["Authorization"]="Bearer "+KEY
MAX_CALLS=24
calls=0
results=[]
LEAGUES=[("Premier League","comp_3039"),("Championship","comp_8321"),("Scottish Premiership","comp_6387")]
YEARS=[2024,2022,2020,2018]
def get(path,params=None):
 global calls
 if calls>=MAX_CALLS: return None
 time.sleep(2)
 try:
  r=S.get(BASE+path,params=params,timeout=30);calls+=1
  print("HTTP",r.status_code,path,"remaining",r.headers.get("X-Monthly-Quota-Remaining","unknown"),flush=True)
  if r.status_code==429: return None
  if r.status_code>=400: return {"_status":r.status_code}
  return r.json()
 except requests.RequestException as e:
  print("REQUEST_ERROR",str(e)[:120]);return None
for name,comp in LEAGUES:
 for year in YEARS:
  if calls+2>MAX_CALLS: break
  p=get("/football/matches",{"competition_id":comp,"status":"finished","date_from":f"{year}-08-01","date_to":f"{year+1}-07-31","per_page":1,"page":1,"sort":"-utc_date"})
  matches=(p or {}).get("data",[])
  if not isinstance(matches,list) or not matches:
   results.append({"league":name,"season":year,"fixture_found":False,"response_status":(p or {}).get("_status")});continue
  match=matches[0];mid=match.get("id") or match.get("match_id")
  if not mid: continue
  o=get(f"/football/matches/{mid}/odds")
  books=((o or {}).get("data") or {}).get("bookmakers") or []
  results.append({"league":name,"season":year,"match_id":mid,"odds_status":(o or {}).get("_status",200),"bookmakers":[{"name":b.get("bookmaker"),"markets":sorted((b.get("markets") or {}).keys())} for b in books]})
  print("PROBE",json.dumps(results[-1]),flush=True)
with open("thestatsapi_availability_probe.json","w") as f:json.dump({"checked_at":datetime.now(timezone.utc).isoformat(),"api_calls":calls,"results":results},f,indent=2)
print("TOTAL REQUESTS",calls,"REPORT thestatsapi_availability_probe.json",flush=True)
