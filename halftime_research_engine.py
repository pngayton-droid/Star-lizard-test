"""Read-only halftime research rates, no live betting recommendation."""
import requests
import streamlit as st
from archive_data_engine import _credentials

@st.cache_data(ttl=1800,max_entries=2,show_spinner=False)
def halftime_sample(competition_id=None,limit=12000):
    url,key=_credentials()
    params={"select":"competition_id,match_date,home_ht_goals,away_ht_goals,home_ht_xg,away_ht_xg,home_goals,away_goals,home_second_half_goals,away_second_half_goals,trailing_side,trailing_ht_xg",
            "order":"match_date.asc","limit":1000}
    if competition_id:
        params["competition_id"]="eq."+str(competition_id)
    records=[]
    for offset in range(0,limit,1000):
        params["offset"]=offset
        response=requests.get(url+"/rest/v1/halftime_research_outcomes",
            headers={"apikey":key,"Authorization":"Bearer "+key},params=params,timeout=30)
        response.raise_for_status()
        batch=response.json()
        records.extend(batch)
        if len(batch)<1000:return records
    if len(records)>=limit:
        raise RuntimeError("Sample limit reached; refusing partial historical rates")
    return records

def rates(rows,min_xg=0.2,deficit=1):
    selected=[]
    for r in rows:
        h,a=int(r["home_ht_goals"]),int(r["away_ht_goals"])
        if abs(h-a)!=deficit or r["trailing_side"] is None:continue
        if float(r["trailing_ht_xg"])<min_xg:continue
        selected.append(r)
    n=len(selected)
    if not n:return {"n":0}
    # Outcomes here are end-of-match 2H goals, not verified first-goal sequence.
    trailing_scored=sum((int(r["home_second_half_goals"]) if r["trailing_side"]=="home" else int(r["away_second_half_goals"]))>0 for r in selected)
    comeback=sum((int(r["home_goals"])>=int(r["away_goals"]) if r["trailing_side"]=="home" else int(r["away_goals"])>=int(r["home_goals"])) for r in selected)
    return {"n":n,"trailing_scored":trailing_scored,"avoided_defeat":comeback,
            "scored_rate":trailing_scored/n,"avoid_rate":comeback/n}
