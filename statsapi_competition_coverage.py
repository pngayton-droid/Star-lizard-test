"""Small read-only StatsAPI historical competition coverage fetch."""
import requests
import streamlit as st
from archive_data_engine import _credentials

@st.cache_data(ttl=1800,max_entries=2,show_spinner=False)
def statsapi_coverage():
    url,key=_credentials()
    response=requests.get(url+"/rest/v1/statsapi_historical_competition_coverage",
        headers={"apikey":key,"Authorization":"Bearer "+key},
        params={"select":"competition_id,matches,xg_matches,home_teams,away_teams",
                "limit":1000},timeout=25)
    response.raise_for_status()
    return {str(row["competition_id"]):row for row in response.json()}
