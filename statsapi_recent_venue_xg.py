"""Read compact, recent historical xG summaries; no full match dataset."""
import requests
import streamlit as st
from archive_data_engine import _credentials

@st.cache_data(ttl=1800,max_entries=2,show_spinner=False)
def recent_venue_xg():
    url,key=_credentials()
    rows=[]
    for offset in range(0,10000,1000):
        response=requests.get(url+"/rest/v1/statsapi_recent_venue_xg_summary",
            headers={"apikey":key,"Authorization":"Bearer "+key},
            params={"select":"competition_id,team_name,venue,sample_n,xg_for_avg,xg_against_avg,last_match_date",
                    "order":"competition_id.asc,team_name.asc,venue.asc","limit":1000,"offset":offset},timeout=25)
        response.raise_for_status()
        batch=response.json()
        rows.extend(batch)
        if len(batch)<1000:return rows
    raise RuntimeError("Recent xG coverage exceeded safety limit")
