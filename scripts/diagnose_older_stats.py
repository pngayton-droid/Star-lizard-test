"""Diagnose older match xG availability without logging credentials or raw personal data."""
import os,requests,json
from supabase import create_client
db=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])
s=requests.Session();s.headers["Authorization"]="Bearer "+os.environ["STATS_API_KEY"]
q=s.get("https://api.thestatsapi.com/api/football/matches",params={"competition_id":"comp_3039","status":"finished","date_from":"2021-08-01","date_to":"2022-07-31","per_page":1,"page":1,"sort":"-utc_date"},timeout=30)
q.raise_for_status();m=q.json()["data"][0];mid=m.get("id") or m.get("match_id")
r=s.get(f"https://api.thestatsapi.com/api/football/matches/{mid}/stats",timeout=30)
print("MATCH",mid,"stats_http",r.status_code,flush=True)
if r.ok:
 d=(r.json().get("data") or {});print("TOP_KEYS",list(d.keys()),flush=True)
 ov=d.get("overview") or {};print("OVERVIEW_KEYS",list(ov.keys()),flush=True)
 print("XG",json.dumps(ov.get("expected_goals"),default=str)[:900],flush=True)
 print("NP_XG",json.dumps(d.get("np_expected_goals"),default=str)[:500],flush=True)
 print("IS_OLD_MATCH",mid not in {x["match_id"] for x in (db.table("historical_xg").select("match_id").eq("match_id",mid).execute().data or [])},flush=True)
else:print("ERROR_BODY",r.text[:300],flush=True)
