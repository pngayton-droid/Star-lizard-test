"""Live fixture discovery bridge: no inferred bookmaker prices."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import streamlit as st
from lightweight_fixture_feed import get_key, fixtures_for_day, fixture_label, kickoff, team_name, API_BASE
import requests
from archive_data_engine import load_coverage
from fixture_coverage_engine import archive_league_summary, classify_fixture

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
try:
    archive_summary=archive_league_summary(load_coverage())
    coverage_ok=True
except Exception as exc:
    st.caption("Coverage diagnostic: "+type(exc).__name__+": "+str(exc)[:350])
    archive_summary=None
    coverage_ok=False
    st.warning("Historical archive unavailable; cannot verify league coverage.")
if coverage_ok:
    st.metric("League-covered fixtures",sum(
        classify_fixture(item,archive_summary)["status"]=="League covered" for item in fixtures))
else:
    st.metric("League-covered fixtures","Unknown")
with st.expander("Competition matching diagnostics"):
    st.caption("Displays competition fields only; no API credentials or personal information.")
    if st.button("Inspect competition identifiers"):
        st.write("Archive league codes:",archive_summary.league.tolist() if coverage_ok else "Unavailable")
        samples=[]
        seen=set()
        for item in fixtures:
            comp=item.get("competition")
            comp_id=item.get("competition_id")
            country=item.get("country")
            marker=str((comp,comp_id,country))
            if marker in seen:
                continue
            seen.add(marker)
            samples.append({"competition":str(comp)[:160],
                            "competition_id":str(comp_id)[:80],
                            "country":str(country)[:80],
                            "match_field_names":list(item.keys())[:30]})
            if len(samples)>=15:
                break
        st.write("Sample competition identifiers:",samples)
        st.caption("If competition is missing or an ID rather than a name, we must map official API competition IDs before filtering.")
with st.expander("API coverage diagnostics"):
    st.caption("Checks the first API response without displaying credentials. Use this to distinguish limited source coverage from a pagination issue.")
    if st.button("Inspect fixture API pagination",key="inspect_fixture_pagination"):
        try:
            response=requests.get(API_BASE+"/football/matches",
                headers={"Authorization":f"Bearer {key}"},
                params={"date_from":day.isoformat(),"date_to":day.isoformat(),
                        "sort":"utc_date","per_page":100,"page":1},timeout=25)
            response.raise_for_status()
            payload=response.json()
            rows=payload.get("data") or []
            metadata=payload.get("meta") or {}
            st.write("First-page match count:",len(rows))
            st.write("Pagination metadata:",metadata)
            st.write("Response top-level fields:",list(payload.keys()))
            st.write("Distinct competitions in returned matches:",
                     len(set(str(x.get("competition")) for x in rows)))
            st.caption("No authorization headers or API credentials are displayed.")
        except Exception as exc:
            st.warning("API diagnostics unavailable: "+type(exc).__name__)

if not fixtures:
    st.info("No fixtures returned for this date.")
    st.stop()
search=st.text_input("Filter by team or competition",placeholder="Team name")
def searchable(item):
    competition=item.get("competition") or {}
    competition_name=competition.get("name","") if isinstance(competition,dict) else str(competition)
    return " ".join([fixture_label(item),competition_name]).lower()
coverage_filter=st.radio("Historical coverage",["Covered leagues only","All fixtures"],
    horizontal=True,index=0 if coverage_ok else 1,disabled=not coverage_ok)
shown=[item for item in fixtures if search.lower().strip() in searchable(item)]
if coverage_ok and coverage_filter=="Covered leagues only":
    shown=[item for item in shown if classify_fixture(item,archive_summary)["status"]=="League covered"]
# Presentation priority only; never exclude leagues from the underlying API results.
PRIORITY_TERMS=(
    "premier league","championship","la liga","primera división",
    "serie a","bundesliga","ligue 1","champions league",
    "europa league","conference league","eredivisie",
    "primeira liga","scottish premiership","league one","league two",
)
def priority(item):
    competition=item.get("competition") or {}
    comp=(competition.get("name","") if isinstance(competition,dict) else str(competition)).lower()
    rank=next((i for i,term in enumerate(PRIORITY_TERMS) if term in comp),len(PRIORITY_TERMS))
    start=kickoff(item)
    return (rank,start.isoformat() if start else "9999",fixture_label(item))
shown=sorted(shown,key=priority)
st.caption(f"Showing {len(shown)} fixtures. Major competitions appear first when the API provides competition names; all returned leagues remain available.")
def label_with_comp(item):
    comp=item.get("competition") or {}
    comp_name=comp.get("name","") if isinstance(comp,dict) else str(comp)
    return fixture_label(item)+(" · "+str(comp_name) if comp_name else "")
labels=[label_with_comp(item) for item in shown]
if not shown:
    st.info("No fixtures match this filter. During international week this may be expected. Select All fixtures to inspect the source feed.")
    st.stop()
index=st.selectbox("Select fixture",range(len(shown)),format_func=lambda i:labels[i])
item=shown[index]
start=kickoff(item)
st.write("**Home:** "+team_name(item,"home"))
st.write("**Away:** "+team_name(item,"away"))
st.write("**Kickoff (UK):** "+(start.strftime("%d %b %Y, %H:%M") if start else "Not supplied"))
st.write("**Match status:** "+str(item.get("status","Unknown")))
if coverage_ok:
    verdict=classify_fixture(item,archive_summary)
    st.write("**Historical coverage:** "+verdict["status"])
    st.write("**Archive matches in league:** "+str(verdict["historical_matches"]))
    st.caption(verdict["reason"])
st.write("**StatsAPI match ID:** "+str(item.get("id","Not supplied")))
st.subheader("Market data readiness")
st.warning("Fixture discovery does not supply a verified, timestamped bookmaker quote or a fixture-specific calibrated fair probability. Neither is being inferred.")
st.info("Next integration: identify supported market-odds endpoints and capture source, bookmaker, market, line and timestamp before calculating value.")
