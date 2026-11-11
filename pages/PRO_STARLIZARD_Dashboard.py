"""PRO STARLIZARD central mobile-first dashboard.

Read-only fixtures and coverage. No fictitious prices or value flags.
"""
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import streamlit as st
from lightweight_fixture_feed import get_key,fixtures_for_day,fixture_label
from statsapi_competition_coverage import statsapi_coverage
from statsapi_team_coverage import team_venue_coverage
from fixture_team_readiness import venue_readiness
from statsapi_recent_venue_xg import recent_venue_xg
from fixture_goals_baseline import baseline

st.set_page_config(page_title="PRO STARLIZARD Dashboard",layout="wide")
st.title("🦎 PRO STARLIZARD")
st.caption("Central match intelligence dashboard — halftime first. Research signals are not betting recommendations.")
st.warning("Live halftime xG, verified next-goal prices and live market quotes are not connected yet. No value alerts will be fabricated.")
st.subheader("Research workspaces")
a,b,c=st.columns(3)
with a:
    st.page_link("pages/Halftime_Pricing_Lab.py",label="🧠 Halftime Pricing Lab")
with b:
    st.page_link("pages/Halftime_Intelligence.py",label="🔎 Halftime Pattern Scanner")
with c:
    st.page_link("pages/Live_Fixture_Bridge.py",label="📅 Live Fixture Bridge")

key=get_key()
if not key:
    st.error("TheStatsAPI key not configured.")
    st.stop()
today=datetime.now(ZoneInfo("Europe/London")).date()
day=st.date_input("Fixture date (UK)",value=today,
    min_value=today-timedelta(days=7),max_value=today+timedelta(days=21))
search=st.text_input("Find team or fixture",placeholder="Search fixtures")
try:
    fixtures=fixtures_for_day(key,day.isoformat())
except Exception as exc:
    st.error("Fixture feed temporarily unavailable.")
    st.code(type(exc).__name__)
    st.stop()
try:
    competitions=statsapi_coverage()
except Exception:
    competitions={}
    st.warning("Historical competition coverage unavailable")
try:
    team_rows=team_venue_coverage()
except Exception:
    team_rows=[]
    st.warning("Team venue coverage unavailable")
ready=[]
covered=[]
for fixture in fixtures:
    history=competitions.get(str(fixture.get("competition_id") or ""))
    if history and int(history.get("matches") or 0)>=500:
        covered.append(fixture)
        if team_rows and venue_readiness(fixture,team_rows).get("status")=="Venue xG sample ready":
            ready.append(fixture)
m1,m2,m3=st.columns(3)
m1.metric("Scheduled fixtures",len(fixtures))
m2.metric("History-covered",len(covered))
m3.metric("Venue xG ready",len(ready))
st.caption("History-covered means at least 500 StatsAPI historical league matches. Venue-ready requires sufficient home and away xG observations.")
st.subheader("Match queue")
try:
    recent_rows=recent_venue_xg() if ready else []
except Exception:
    recent_rows=[]
    st.warning("Recent xG summary unavailable; match queue remains accessible.")

show=ready if st.toggle("Only venue-ready fixtures",value=True) else covered
if search.strip():
    show=[f for f in show if search.lower() in fixture_label(f).lower()]
st.caption(f"Showing {min(len(show),80)} of {len(show)} matching fixtures.")
if not show:
    st.info("No matches match these filters. Switch off the venue-ready filter to inspect wider coverage.")
for fixture in show[:80]:
    label=fixture_label(fixture)
    with st.expander(label):
        st.write("Competition ID:",str(fixture.get("competition_id") or "Unavailable"))
        st.write("Venue xG:",venue_readiness(fixture,team_rows).get("status") if team_rows else "Unavailable")
        if fixture in ready and recent_rows:
            research=baseline(fixture,recent_rows)
            if research:
                st.write(f'Pre-match baseline xG: home **{research["home_xg"]:.2f}**, away **{research["away_xg"]:.2f}**')
                st.write(f'Mechanical pre-match Over 2.5 probability: **{research["over_2_5"]*100:.1f}%**')
                st.caption(f'Home venue sample: {research["home_n"]}; away venue sample: {research["away_n"]}. Simple Poisson baseline, not calibrated fair odds.')
        st.caption("Live halftime state and market odds: not yet connected. No value inference.")
st.divider()
st.subheader("Model build status")
st.write("**Working:** fixture discovery, historical coverage, venue sample checks, halftime outcome research, conditional scenario estimates.")
st.write("**In progress:** fixture-calibrated halftime probabilities, verified goal sequence markets, real-time halftime feed, timestamped bookmaker/exchange odds and validated alert ranking.")
st.caption("No opportunities are labelled value until live prices and prospective validation are available.")
