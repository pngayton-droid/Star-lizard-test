"""Lightweight TheStatsAPI fixture feed, without historical-model imports."""
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
import streamlit as st

API_BASE="https://api.thestatsapi.com/api"
UK=ZoneInfo("Europe/London")
KEY_NAMES=("STATS_API_KEY","THESTATSAPI_KEY","THE_STATS_API_KEY","THESTATS_API_KEY","STATSAPI_KEY")

def get_key():
    for name in KEY_NAMES:
        key=st.secrets.get(name)
        if key: return str(key).strip()
    return None

@st.cache_data(ttl=300,max_entries=4,show_spinner=False)
def fixtures_for_day(key,day):
    result=[]
    for page in range(1,21):
        response=requests.get(API_BASE+"/football/matches",
            headers={"Authorization":f"Bearer {key}"},
            params={"date_from":day,"date_to":day,"sort":"utc_date","per_page":100,"page":page},
            timeout=25)
        response.raise_for_status()
        payload=response.json()
        result.extend(payload.get("data") or [])
        total_pages=int((payload.get("meta") or {}).get("total_pages") or 1)
        if page>=total_pages:
            return result
    raise RuntimeError("Fixture pagination exceeded 20-page safety limit")

def kickoff(item):
    raw=item.get("utc_date")
    if not raw:return None
    try:return datetime.fromisoformat(str(raw).replace("Z","+00:00")).astimezone(UK)
    except (ValueError,TypeError):return None

def team_name(item,side):
    team=item.get(side+"_team") or {}
    return str(team.get("name") or "Unknown") if isinstance(team,dict) else str(team)

def fixture_label(item):
    start=kickoff(item)
    clock=start.strftime("%H:%M") if start else "--:--"
    score=item.get("score") or {}
    home,away=score.get("home"),score.get("away")
    result=f" [{home}-{away}]" if home is not None and away is not None else ""
    return f"{clock} {team_name(item,'home')} v {team_name(item,'away')}{result} ({item.get('status','unknown')})"
