"""Small historical team/venue coverage summary; no full match archive loaded."""
import requests
import streamlit as st
from archive_data_engine import _credentials

@st.cache_data(ttl=1800,max_entries=2,show_spinner=False)
def team_venue_coverage():
    url,key=_credentials()
    headers={"apikey":key,"Authorization":"Bearer "+key}
    rows=[]
    for offset in range(0,10000,1000):
        response=requests.get(url+"/rest/v1/statsapi_team_venue_coverage",
            headers=headers,params={"select":"competition_id,team_name,home_matches,away_matches,home_xg_matches,away_xg_matches",
                                    "order":"competition_id.asc,team_name.asc","limit":1000,"offset":offset},timeout=25)
        response.raise_for_status()
        batch=response.json()
        rows.extend(batch)
        if len(batch)<1000:break
    else:
        raise RuntimeError("Team coverage exceeded row safety limit")
    return rows
