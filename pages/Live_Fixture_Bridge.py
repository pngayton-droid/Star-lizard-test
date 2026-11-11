"""Live fixture discovery bridge: no inferred bookmaker prices."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import streamlit as st
from starlizard_live_fixtures import get_key, fixtures_for_day, fixture_label, kickoff, team_name

st.set_page_config(page_title="Live Fixture Bridge",layout="wide")
st.title("🦎 Live Fixture Bridge")
st.caption("Actual scheduled fixtures from TheStatsAPI. No invented bookmaker quotes or value signals.")
key=get_key()
if not key:
    st.error("StatsAPI credentials are not configured in Streamlit secrets.")
    st.stop()
uk=ZoneInfo("Europe/London")
today=datetime.now(uk).date()
day=st.date_input("Fixture date (UK)",value=today,min_value=today-timedelta(days=7),
                  max_value=today+timedelta(days=21))
st.caption("Fixture discovery cached for five minutes to protect API rate limits.")
try:
    fixtures=fixtures_for_day(key,day.isoformat())
except Exception as exc:
    st.error("TheStatsAPI fixture request failed. Please retry later.")
    st.code(str(exc))
    st.stop()
st.metric("Fixtures returned",len(fixtures))
if not fixtures:
    st.info("No fixtures returned for this date.")
    st.stop()
search=st.text_input("Filter by team or competition",placeholder="Team name")
def searchable(item):
    competition=item.get("competition") or {}
    competition_name=competition.get("name","") if isinstance(competition,dict) else str(competition)
    return " ".join([fixture_label(item),competition_name]).lower()
shown=[item for item in fixtures if search.lower().strip() in searchable(item)]
st.caption(f"Showing {len(shown)} fixtures")
labels=[fixture_label(item) for item in shown]
if not shown:
    st.info("No fixtures match your filter.")
    st.stop()
index=st.selectbox("Select fixture",range(len(shown)),format_func=lambda i:labels[i])
item=shown[index]
start=kickoff(item)
st.write("**Home:** "+team_name(item,"home"))
st.write("**Away:** "+team_name(item,"away"))
st.write("**Kickoff (UK):** "+(start.strftime("%d %b %Y, %H:%M") if start else "Not supplied"))
st.write("**Match status:** "+str(item.get("status","Unknown")))
st.write("**StatsAPI match ID:** "+str(item.get("id","Not supplied")))
st.subheader("Market data readiness")
st.warning("Fixture discovery does not supply a verified, timestamped bookmaker quote or a fixture-specific calibrated fair probability. Neither is being inferred.")
st.info("Next integration: identify supported market-odds endpoints and capture source, bookmaker, market, line and timestamp before calculating value.")
