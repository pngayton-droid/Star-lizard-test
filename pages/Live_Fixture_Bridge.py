"""Live fixture discovery bridge: no inferred bookmaker prices."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import streamlit as st
from lightweight_fixture_feed import get_key, fixtures_for_day, fixture_label, kickoff, team_name, API_BASE
import requests
from archive_data_engine import load_coverage
from fixture_coverage_engine import archive_league_summary, classify_fixture
from statsapi_competition_coverage import statsapi_coverage
from statsapi_team_coverage import team_venue_coverage
from fixture_team_readiness import venue_readiness
from statsapi_recent_venue_xg import recent_venue_xg
from fixture_goals_baseline import baseline

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
    archive_ok=True
except Exception:
    archive_summary=None
    archive_ok=False
try:
    api_history=statsapi_coverage()
    history_ok=True
except Exception as exc:
    api_history={}
    history_ok=False
    st.warning("StatsAPI historical coverage lookup unavailable: "+type(exc).__name__)
coverage_ok=archive_ok or history_ok
def coverage(item):
    comp_id=str(item.get("competition_id") or "")
    row=api_history.get(comp_id)
    if row and int(row.get("matches") or 0)>=500:
        return {"status":"StatsAPI history","historical_matches":int(row["matches"]),
                "reason":"Direct competition ID match; team-level readiness not yet checked"}
    if archive_ok:
        return classify_fixture(item,archive_summary)
    return {"status":"Unmatched","historical_matches":0,"reason":"No verified coverage match"}
st.metric("League-covered fixtures",sum(coverage(item)["status"] in ("StatsAPI history","League covered") for item in fixtures) if coverage_ok else "Unknown")
st.caption("Coverage matches the StatsAPI historical competition IDs directly; the imported archive is a secondary source. Minimum 500 historical matches.")
try:
    team_rows=team_venue_coverage()
    team_data_ok=True
except Exception as exc:
    team_rows=[]
    team_data_ok=False
    st.warning("Team history summary unavailable: "+type(exc).__name__)
if team_data_ok:
    covered_items=[item for item in fixtures if coverage(item)["status"] in ("StatsAPI history","League covered")]
    readiness=[venue_readiness(item,team_rows) for item in covered_items]
    st.metric("Team/venue xG sample ready",sum(x["status"]=="Venue xG sample ready" for x in readiness))
    st.caption("At least 8 home/away xG samples required; unmatched team names are not assumed to be ready.")

with st.expander("Competition API lookup test"):
    st.caption("One on-demand request to check how TheStatsAPI identifies competitions. No credentials displayed.")
    ids=list(dict.fromkeys(str(item.get("competition_id")) for item in fixtures if item.get("competition_id")))
    if ids and st.button("Test competition lookup"):
        sample_id=ids[0]
        try:
            response=requests.get(API_BASE+"/football/competitions/"+sample_id,
                headers={"Authorization":f"Bearer {key}"},timeout=20)
            st.write("Lookup HTTP status:",response.status_code)
            if response.ok:
                payload=response.json()
                data=payload.get("data") if isinstance(payload,dict) else None
                if isinstance(data,dict):
                    st.write("Competition name:",data.get("name"))
                    st.write("Competition country:",data.get("country") or data.get("country_name"))
                    st.write("Available competition fields:",list(data.keys()))
                else:
                    st.write("Response fields:",list(payload.keys()) if isinstance(payload,dict) else "Non-object response")
            else:
                st.info("The API may require a different competition lookup endpoint. No further requests were made.")
        except Exception as exc:
            st.warning("Lookup unavailable: "+type(exc).__name__)
with st.expander("Competition matching diagnostics"):
    st.caption("Displays competition fields only; no API credentials or personal information.")
    if st.button("Inspect competition identifiers"):
        st.write("Archive league codes:",archive_summary.league.tolist() if archive_ok else "Unavailable")
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
    shown=[item for item in shown if coverage(item)["status"] in ("StatsAPI history","League covered")]
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
    verdict=coverage(item)
    st.write("**Historical coverage:** "+verdict["status"])
    st.write("**Archive matches in league:** "+str(verdict["historical_matches"]))
    st.caption(verdict["reason"])
    if team_data_ok:
        team_check=venue_readiness(item,team_rows)
        st.write("**Team/venue readiness:** "+team_check["status"])
        st.write("**Home team home matches:** "+str(team_check["home_games"]))
        st.write("**Away team away matches:** "+str(team_check["away_games"]))
        st.write("**Home xG samples:** "+str(team_check["home_xg"]))
        st.write("**Away xG samples:** "+str(team_check["away_xg"]))
st.write("**StatsAPI match ID:** "+str(item.get("id","Not supplied")))
st.subheader("Experimental fixture goals baseline")
st.caption("Recent venue xG only: arithmetic attack/defence blend and independent Poisson goals. Not calibrated or opposition-adjusted.")
if st.button("Calculate historical goals baseline for selected fixture"):
    try:
        estimate=baseline(item,recent_venue_xg())
        if not estimate:
            st.info("Insufficient matched venue xG samples for this fixture.")
        else:
            a,b,c=st.columns(3)
            a.metric("Home expected goals",f'{estimate["home_xg"]:.2f}')
            b.metric("Away expected goals",f'{estimate["away_xg"]:.2f}')
            c.metric("Total expected goals",f'{estimate["total_xg"]:.2f}')
            for market in ("over_1_5","over_2_5"):
                p=estimate[market]
                st.write(f'**{market.replace("_"," ").title()}**: {p*100:.1f}% · mechanical odds {1/p:.2f}' if p>0 else "Probability unavailable")
            st.caption(f'Home venue sample: {estimate["home_n"]} (latest {estimate["home_last"]}); away venue sample: {estimate["away_n"]} (latest {estimate["away_last"]}).')
            st.warning("Mechanical probabilities are NOT fair odds or betting recommendations. No bookmaker odds, lineup information, uncertainty calibration, or backtested predictive accuracy is included.")
    except Exception as exc:
        st.warning("Historical baseline unavailable: "+type(exc).__name__)
st.subheader("Market data readiness")
st.warning("Fixture discovery does not supply a verified, timestamped bookmaker quote or a fixture-specific calibrated fair probability. Neither is being inferred.")
st.info("Next integration: identify supported market-odds endpoints and capture source, bookmaker, market, line and timestamp before calculating value.")
