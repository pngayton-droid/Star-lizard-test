"""Read-only, explicitly labelled second-half first-scorer research.

NULL outcomes are excluded: NULL may mean no second-half goal or unavailable
sequence data, so treating NULL as a loss would invent outcomes.
"""
import requests
import streamlit as st
from archive_data_engine import _credentials

@st.cache_data(ttl=1800,max_entries=2,show_spinner=False)
def labelled_next_goal_rows():
    url,key=_credentials()
    headers={"apikey":key,"Authorization":"Bearer "+key}
    result=[]
    for offset in range(0,12000,1000):
        params={"select":"match_id,match_date,home_ht_goals,away_ht_goals,home_ht_xg,away_ht_xg,trailing_side,trailing_team_scored_first",
                "trailing_side":"not.is.null",
                "trailing_team_scored_first":"not.is.null",
                "order":"match_date.asc,match_id.asc","limit":1000,"offset":offset}
        response=requests.get(url+"/rest/v1/starlizard_next_goal_research",
            headers=headers,params=params,timeout=30)
        response.raise_for_status()
        batch=response.json()
        result.extend(batch)
        if len(batch)<1000:return result
    raise RuntimeError("Labelled next-goal query exceeded safe pagination cap")

def trailing_first_summary(rows,min_xg=0.2,deficit=1,side="both"):
    if side not in ("both","home","away"):raise ValueError("Invalid side")
    if deficit<1 or min_xg<0:raise ValueError("Invalid filter")
    selected=[]
    for row in rows:
        if row.get("trailing_team_scored_first") is None:continue
        trailing=row.get("trailing_side")
        if trailing not in ("home","away") or (side!="both" and side!=trailing):continue
        try:
            h,a=int(row["home_ht_goals"]),int(row["away_ht_goals"])
            if abs(h-a)!=deficit or (h>a and trailing!="away") or (a>h and trailing!="home"):continue
            xg=float(row["home_ht_xg"] if trailing=="home" else row["away_ht_xg"])
        except (TypeError,ValueError,KeyError):continue
        if xg>=min_xg:selected.append(row)
    n=len(selected)
    wins=sum(row["trailing_team_scored_first"] is True for row in selected)
    return {"n":n,"hits":wins,"rate":wins/n if n else None}
