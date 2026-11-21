"""Four-fixture pre-kickoff odds trial; API limit 12, no historical table writes."""
import os,time,datetime as dt,requests,unicodedata
from supabase import create_client
DAY="2026-11-20"
TARGETS=[
 ("comp_4643","bayern","koln","Bayern Munich v Cologne"),
 ("comp_0256","troyes","le havre","Troyes v Le Havre"),
 ("comp_8531","cercle","westerlo","Cercle Brugge v Westerlo"),
 ("comp_8814","athletic","espanyol","Athletic Bilbao v Espanyol")]
s=requests.Session();s.headers["Authorization"]="Bearer "+os.environ["STATS_API_KEY"]
db=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])
calls=0
def get(path,params=None):
 global calls
 if calls>=12:raise RuntimeError("12 request cap reached")
 r=s.get("https://api.thestatsapi.com/api"+path,params=params,timeout=25);calls+=1
 q=r.headers.get("X-Monthly-Quota-Remaining")
 if q is not None and int(q)<=500:raise RuntimeError("Quota reserve reached")
 if r.status_code in (404,409,429):print("HTTP",r.status_code,path);return None
 r.raise_for_status();return r.json().get("data")
def norm(value):
 return "".join(c for c in unicodedata.normalize("NFKD",str(value).lower()) if not unicodedata.combining(c)).replace("ö","o")
def main():
 now=dt.datetime.now(dt.timezone.utc)
 if now.date().isoformat()!=DAY:return
 found=[]
 for cid,home,away,label in TARGETS:
  matches=get("/football/matches",{"competition_id":cid,"date_from":DAY,"date_to":DAY,"per_page":100})
  if not isinstance(matches,list):continue
  matching=[m for m in matches if home in str((m.get("home_team") or {}).get("name","")).lower() and (away in norm((m.get("away_team") or {}).get("name","")) or (away=="koln" and "cologne" in norm((m.get("away_team") or {}).get("name",""))))]
  if len(matching)!=1:
   print("Match unresolved",label,len(matching));continue
  m=matching[0]
  try:kickoff=dt.datetime.fromisoformat(m["utc_date"].replace("Z","+00:00"))
  except (KeyError,ValueError,TypeError):continue
  found.append((kickoff,m,label,cid))
 for kickoff,m,label,cid in sorted(found):
  target=kickoff-dt.timedelta(minutes=5)
  delay=(target-dt.datetime.now(dt.timezone.utc)).total_seconds()
  if delay>0:time.sleep(min(delay,3600))
  actual=dt.datetime.now(dt.timezone.utc)
  lag=(actual-target).total_seconds()
  if abs(lag)>180:
   print("Missed 5-minute window",label,"offset_seconds",round(lag));continue
  if not m.get("odds_available"):
   print("No pre-match odds flag",label);continue
  data=get("/football/matches/"+m["id"]+"/odds",{"bookmaker":"bet365,betfair-exchange,pinnacle"})
  if not isinstance(data,dict):continue
  rows=[]
  for book in data.get("bookmakers") or []:
   if not isinstance(book,dict):continue
   name=book.get("bookmaker");markets=book.get("markets")
   if name and isinstance(markets,dict):
    rows.append({"match_id":m["id"],"fixture":label,"competition_id":cid,
     "observed_at":actual.isoformat(),"match_status":"scheduled",
     "elapsed_minutes":None,"bookmaker":name,"markets":markets,
     "snapshot_kind":"prematch_target_minus_5m"})
  if rows:db.table("ht_odds_trial_20261120").insert(rows).execute()
  print(label,"bookmakers",len(rows),"offset_seconds",round(lag),"calls",calls,flush=True)
 print("FINISHED",calls)
if __name__=="__main__":main()
