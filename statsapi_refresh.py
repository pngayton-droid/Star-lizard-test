"""Optional bounded TheStatsAPI refresh into the existing Supabase historical store."""
from datetime import date,timedelta
import time
import requests
from supabase import create_client
import streamlit as st

BASE="https://api.thestatsapi.com/api"
LEAGUES={"Premier League":"comp_3039","Championship":"comp_8321","La Liga":"comp_8814","Serie A":"comp_5840","Bundesliga":"comp_4643","Ligue 1":"comp_0256","Eredivisie":"comp_3809","Primeira Liga":"comp_8385","Belgian Pro League":"comp_8531","Scottish Premiership":"comp_6387"}
def settings():
    key=st.secrets.get("STATS_API_KEY") or st.secrets.get("THESTATSAPI_KEY")
    url=st.secrets.get("SUPABASE_URL")
    secret=st.secrets.get("SUPABASE_SECRET_KEY")
    return key,url,secret
def refresh(league="Premier League",days=21,max_matches=25):
    key,url,secret=settings()
    if not all((key,url,secret)):
        raise RuntimeError("Missing STATS_API_KEY, SUPABASE_URL or SUPABASE_SECRET_KEY in Streamlit secrets. No requests were sent.")
    db=create_client(url,secret)
    session=requests.Session()
    session.headers.update({"Authorization":f"Bearer {key}"})
    calls=0
    def get(path,params=None):
        nonlocal calls
        for attempt in range(3):
            if calls>=65:raise RuntimeError("Safety cap reached: 65 API calls.")
            response=session.get(BASE+path,params=params,timeout=25)
            calls+=1
            if response.status_code==429:
                time.sleep(min(30,max(1,int(response.headers.get("Retry-After","10")))))
                continue
            response.raise_for_status()
            return response.json().get("data")
        raise RuntimeError("API rate limit persisted; try again later.")
    since=(date.today()-timedelta(days=days)).isoformat()
    payload=get("/football/matches",{"competition_id":LEAGUES[league],"status":"finished","date_from":since,"date_to":date.today().isoformat(),"per_page":50,"page":1,"sort":"-utc_date"})
    matches=payload if isinstance(payload,list) else []
    saved=0;skipped=0;errors=[]
    for match in matches[:max_matches]:
        match_id=str(match.get("id") or match.get("match_id") or "")
        home=match.get("home_team") or {}
        away=match.get("away_team") or {}
        if not match_id or not home.get("name") or not away.get("name"):
            skipped+=1;continue
        try:
            stats=get(f"/football/matches/{match_id}/stats")
            if not isinstance(stats,dict):skipped+=1;continue
            overview=stats.get("overview") or {}
            xg=(overview.get("expected_goals") or {})
            full=xg.get("all") or {}
            half=xg.get("first_half") or {}
            existing=db.table("historical_xg").select("match_id").eq("match_id",match_id).limit(1).execute().data
            # Do not overwrite existing match scores or other fields.
            record={"match_id":match_id,"match_date":str(match.get("utc_date") or "")[:10],"home_team":home["name"],"away_team":away["name"],"competition_id":LEAGUES[league]}
            if not existing:
                db.table("historical_xg").upsert(record,on_conflict="match_id").execute()
            update={}
            for col,value in [("home_xg",full.get("home")),("away_xg",full.get("away")),("home_ht_xg",half.get("home")),("away_ht_xg",half.get("away"))]:
                if value is not None:update[col]=value
            if update:db.table("historical_xg").update(update).eq("match_id",match_id).execute()
            db.table("historical_match_events").upsert({"match_id":match_id,"stats_data":stats,"stats_status":200},on_conflict="match_id").execute()
            saved+=1
        except Exception as exc:
            errors.append(f"{match_id}: {str(exc)[:110]}")
        time.sleep(.5)
    return {"matches_listed":len(matches),"saved_stats":saved,"skipped":skipped,"api_calls":calls,"errors":errors}
