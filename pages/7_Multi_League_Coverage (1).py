"""Pro Star Lizard — verify TheStatsAPI league coverage before bulk collection."""
import os
import time
import json
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Star Lizard | League Coverage", layout="centered")
st.title("Pro Star Lizard | Multi-League Coverage")
st.caption("First verify actual API coverage. This page does not assume xG or odds are available for every league.")
key = st.secrets.get("STATS_API_KEY", os.environ.get("STATS_API_KEY", ""))
if not key:
    st.error("STATS_API_KEY missing from Streamlit secrets. Never paste it into chat.")
    st.stop()

TARGETS = {
    "England": ["Premier League", "Championship"],
    "Spain": ["La Liga", "Primera Division"],
    "Germany": ["Bundesliga"],
    "Italy": ["Serie A"],
    "France": ["Ligue 1"],
    "Netherlands": ["Eredivisie"],
    "Portugal": ["Primeira Liga", "Liga Portugal"],
    "Belgium": ["Pro League", "Jupiler Pro League"],
    "Scotland": ["Premiership", "Scottish Premiership"],
}
st.write("**Target:** 10 competitions across nine countries.")
st.info("Coverage listing is not proof of historical xG, corners, cards or bookmaker odds availability. Those require separate checks.")
if "league_coverage_raw" not in st.session_state:
    st.session_state.league_coverage_raw = None
if "league_coverage_error" not in st.session_state:
    st.session_state.league_coverage_error = None

if st.button("Check API league coverage", type="primary"):
    try:
        r = requests.get(
            "https://api.thestatsapi.com/api/coverage/leagues",
            headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
            timeout=35,
        )
        if r.status_code == 200:
            payload = r.json()
            st.session_state.league_coverage_raw = payload
            st.session_state.league_coverage_error = None
        elif r.status_code == 429:
            st.session_state.league_coverage_error = (
                "API rate limit (429). Wait before trying again; no repeated requests were sent."
            )
        else:
            st.session_state.league_coverage_error = f"HTTP {r.status_code}: {r.text[:250]}"
    except (requests.RequestException, ValueError) as exc:
        st.session_state.league_coverage_error = str(exc)

if st.session_state.league_coverage_error:
    st.error(st.session_state.league_coverage_error)
payload = st.session_state.league_coverage_raw
if payload is None:
    st.stop()

def find_league_records(node, depth=0):
    """Accept list or nested data wrappers; do not manufacture missing IDs."""
    if depth > 7:
        return []
    if isinstance(node, list):
        result = []
        for item in node:
            result.extend(find_league_records(item, depth+1))
        return result
    if isinstance(node, dict):
        name = node.get("name") or node.get("league_name") or node.get("competition_name")
        if isinstance(name, str) and (node.get("id") or node.get("league_id") or node.get("competition_id")):
            return [node]
        result = []
        for v in node.values():
            if isinstance(v, (dict, list)):
                result.extend(find_league_records(v, depth+1))
        return result
    return []

records = find_league_records(payload)
if not records:
    st.warning("API responded, but the league-list structure wasn't recognised. Download the response and share it so we can adapt the parser.")
    st.download_button("Download coverage response (JSON)", json.dumps(payload, indent=2), "starlizard_coverage_response.json", "application/json")
    st.stop()

rows = []
for rec in records:
    country_obj = rec.get("country") or rec.get("country_name") or rec.get("region") or ""
    country = country_obj.get("name", "") if isinstance(country_obj, dict) else str(country_obj)
    rows.append({
        "League": str(rec.get("name") or rec.get("league_name") or rec.get("competition_name") or ""),
        "Country": country,
        "API league ID": str(rec.get("id") or rec.get("league_id") or rec.get("competition_id") or ""),
        "Season info": str(rec.get("seasons") or rec.get("season") or "")[:100],
    })
df = pd.DataFrame(rows).drop_duplicates()
st.success(f"Retrieved {len(df)} distinct league records.")
st.subheader("Search league coverage")
term = st.text_input("Search by league or country", "")
visible = df[df["League"].str.contains(term, case=False, regex=False) | df["Country"].str.contains(term, case=False, regex=False)] if term else df
st.dataframe(visible, use_container_width=True, hide_index=True)
st.download_button("Download league coverage CSV", df.to_csv(index=False), "starlizard_league_coverage.csv", "text/csv")

st.subheader("Our target leagues")
for country, names in TARGETS.items():
    matches = df[df["League"].apply(lambda x: any(n.lower() in x.lower() or x.lower() in n.lower() for n in names))]
    # Name-only matching is tentative: country information can be absent or formatted differently.
    if country.lower() in " ".join(df["Country"].str.lower().tolist()):
        matches = matches[matches["Country"].str.contains(country, case=False, regex=False)]
    st.write(f"**{country}:** " + (", ".join(matches["League"].head(4).tolist()) if not matches.empty else "Not matched — check list manually"))
st.caption("Name matching is indicative, not confirmation of detailed stats. Next phase: test sample match/stats coverage per league before building a persistent ratings database.")
with st.expander("Raw API response (technical)"):
    st.json(payload)
