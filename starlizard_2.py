"""PRO STARLIZARD 2.0 — existing TheStatsAPI records only.
Read-only Supabase dashboard. No calls to TheStatsAPI; no new leagues downloaded.
Run with: streamlit run starlizard_2.py
"""
import streamlit as st
import pandas as pd
from supabase import create_client
from research.chronological_validation import chronological_split, evaluate_binary_baseline, wilson_interval

st.set_page_config(page_title="PRO STARLIZARD 2.0", page_icon="⚽", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>
.stApp{background:#0b1220;color:#edf3ff}
.block-container{max-width:1150px;padding-top:1.8rem}
div[data-testid="stMetric"]{background:#172238;padding:15px;border-radius:12px;border:1px solid #33435c}
</style>""", unsafe_allow_html=True)
st.image("pro_starlizard_header_correct-1.png", use_container_width=True)
st.title("PRO STARLIZARD 2.0")
st.caption("Existing TheStatsAPI data only · Read-only research · No new API collection")

@st.cache_resource
def db():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SECRET_KEY"])

@st.cache_data(ttl=900)
def total(table):
    return db().table(table).select("match_id", count="exact").limit(1).execute().count or 0

@st.cache_data(ttl=900)
def league_inventory():
    # Query only existing database rows; aggregate from locally stored xG history.
    # Fetch all pages rather than silently treating the first 1,000 as the full archive.
    rows=[]
    for offset in range(0, 100000, 1000):
        batch=(db().table("historical_xg")
               .select("match_id,competition_id,match_date")
               .order("match_id")
               .range(offset,offset+999).execute().data or [])
        rows.extend(batch)
        if len(batch)<1000:
            break
    if not rows:
        return pd.DataFrame(columns=["League ID","Matches","First match","Last match"])
    df=pd.DataFrame(rows).drop_duplicates("match_id")
    df["match_date"]=pd.to_datetime(df["match_date"],errors="coerce")
    out=(df.groupby("competition_id",dropna=False)
         .agg(Matches=("match_id","count"),first=("match_date","min"),last=("match_date","max"))
         .reset_index().rename(columns={"competition_id":"League ID","first":"First match","last":"Last match"}))
    return out.sort_values("Matches",ascending=False)

LEAGUE_NAMES = {
    "comp_8321":"England · Championship",
    "comp_3039":"England · Premier League",
    "comp_5840":"Italy · Serie A",
    "comp_8814":"Spain · La Liga",
    "comp_0256":"France · Ligue 1",
    "comp_4643":"Germany · Bundesliga",
    "comp_8531":"Belgium · Pro League",
    "comp_3809":"Netherlands · Eredivisie",
    "comp_8385":"Portugal · Primeira Liga",
    "comp_6387":"Scotland · Premiership",
}

tab1,tab2,tab3,tab4,tab5,tab6,tab7=st.tabs(["🏠 Overview","🏆 Existing leagues","📊 Data coverage","🧪 HT research","📐 Holdout test","💷 Odds quality","🔬 Pattern search"])
with tab1:
    st.subheader("Our existing football database")
    try:
        a,b,c=st.columns(3)
        a.metric("Event timeline records",f"{total('historical_match_events'):,}")
        b.metric("Historical odds records",f"{total('historical_match_odds'):,}")
        c.metric("Historical xG records",f"{total('historical_xg'):,}")
    except Exception as exc:
        st.error(f"Database connection unavailable: {type(exc).__name__}")
    st.info("No fresh API requests are made by this dashboard. Existing collectors and credentials are unchanged.")
    st.warning("No betting edge is currently verified by this dashboard. Prices and signals must pass out-of-sample testing.")
with tab2:
    st.subheader("Leagues already in our stored data")
    try:
        leagues=league_inventory()
        leagues.insert(0,"League",leagues["League ID"].map(LEAGUE_NAMES).fillna("Unassigned"))
        st.metric("Identified leagues",int(leagues["League ID"].notna().sum()))
        selection = st.multiselect(
            "Compare leagues",
            options=leagues["League"].tolist(),
            default=leagues["League"].tolist(),
        )
        selected = leagues[leagues["League"].isin(selection)].copy()
        st.dataframe(selected,use_container_width=True,hide_index=True)
        if not selected.empty:
            st.bar_chart(selected.set_index("League")["Matches"],horizontal=True)
            st.metric("Matches in selected leagues",f"{int(selected['Matches'].sum()):,}")
        st.caption("Inventory comes from historical_xg; event/odds coverage can differ. No leagues are fetched from TheStatsAPI.")
    except Exception as exc:
        st.error(f"League inventory unavailable: {type(exc).__name__}")
@st.cache_data(ttl=900)
def coverage_ids(table):
    ids = set()
    for offset in range(0, 100000, 1000):
        batch = (db().table(table).select("match_id")
                 .order("match_id").range(offset, offset + 999).execute().data or [])
        ids.update(str(row["match_id"]) for row in batch if row.get("match_id") is not None)
        if len(batch) < 1000:
            break
    return ids

@st.cache_data(ttl=900)
def coverage_by_league():
    odds_ids = coverage_ids("historical_match_odds")
    event_ids = coverage_ids("historical_match_events")
    rows = []
    for offset in range(0, 100000, 1000):
        batch = (db().table("historical_xg")
                 .select("match_id,competition_id,home_xg,away_xg,home_ht_xg,away_ht_xg")
                 .order("match_id").range(offset, offset + 999).execute().data or [])
        for m in batch:
            match_id = str(m["match_id"])
            rows.append({
                "League": LEAGUE_NAMES.get(m.get("competition_id"), "Unassigned"),
                "Match ID": match_id,
                "Odds stored": int(match_id in odds_ids),
                "Events stored": int(match_id in event_ids),
                "Full-time xG": int(m.get("home_xg") is not None and m.get("away_xg") is not None),
                "Half-time xG": int(m.get("home_ht_xg") is not None and m.get("away_ht_xg") is not None),
            })
        if len(batch) < 1000:
            break
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows).drop_duplicates("Match ID")
    return (frame.groupby("League", as_index=False)
            .agg(Matches=("Match ID", "count"),
                 Odds_records=("Odds stored", "sum"),
                 Event_records=("Events stored", "sum"),
                 FT_xG=("Full-time xG", "sum"),
                 HT_xG=("Half-time xG", "sum"))
            .sort_values("Matches", ascending=False))

with tab3:
    st.subheader("Stored match data coverage")
    st.caption("Matches joined by match ID across existing Supabase tables. Odds record presence does not guarantee usable prices.")
    if st.button("Run read-only coverage audit", type="primary"):
        try:
            report = coverage_by_league()
            st.dataframe(report, use_container_width=True, hide_index=True)
            st.download_button("Download coverage CSV", report.to_csv(index=False), "starlizard_coverage.csv", "text/csv")
        except Exception as exc:
            st.error(f"Coverage audit failed: {type(exc).__name__}: {exc}")
    st.info("No external StatsAPI requests. The audit reads stored Supabase records only.")

@st.cache_data(ttl=900)
def halftime_research_data():
    """Read existing StatsAPI match outcomes only; no odds or API calls."""
    records = []
    fields = ("match_id,competition_id,match_date,home_ht_goals,away_ht_goals,"
              "home_goals,away_goals,home_ht_xg,away_ht_xg")
    for offset in range(0, 100000, 1000):
        batch = (db().table("historical_xg").select(fields)
                 .order("match_id").range(offset, offset + 999).execute().data or [])
        records.extend(batch)
        if len(batch) < 1000:
            break
    if not records:
        return pd.DataFrame()
    frame = pd.DataFrame(records).drop_duplicates("match_id")
    numeric = ["home_ht_goals", "away_ht_goals", "home_goals", "away_goals",
               "home_ht_xg", "away_ht_xg"]
    for field in numeric:
        frame[field] = pd.to_numeric(frame[field], errors="coerce")
    # No outcome imputation: remove matches missing any required score.
    frame = frame.dropna(subset=numeric[:4]).copy()
    frame["League"] = frame["competition_id"].map(LEAGUE_NAMES).fillna("Unassigned")
    frame["HT score"] = frame["home_ht_goals"].astype(int).astype(str) + "-" + frame["away_ht_goals"].astype(int).astype(str)
    frame["HT state"] = "Draw"
    frame.loc[frame.home_ht_goals > frame.away_ht_goals, "HT state"] = "Home leading"
    frame.loc[frame.home_ht_goals < frame.away_ht_goals, "HT state"] = "Away leading"
    frame["2H home goals"] = frame.home_goals - frame.home_ht_goals
    frame["2H away goals"] = frame.away_goals - frame.away_ht_goals
    # Reject inconsistent score records, rather than manufacturing negative goals.
    frame = frame[(frame["2H home goals"] >= 0) & (frame["2H away goals"] >= 0)].copy()
    frame["Both halves home scored"] = ((frame.home_ht_goals > 0) & (frame["2H home goals"] > 0)).astype(int)
    frame["Both halves away scored"] = ((frame.away_ht_goals > 0) & (frame["2H away goals"] > 0)).astype(int)
    frame["Home won both halves"] = ((frame.home_ht_goals > frame.away_ht_goals) &
                                     (frame["2H home goals"] > frame["2H away goals"])).astype(int)
    frame["Away won both halves"] = ((frame.away_ht_goals > frame.home_ht_goals) &
                                     (frame["2H away goals"] > frame["2H home goals"])).astype(int)
    frame["2H draw"] = (frame["2H home goals"] == frame["2H away goals"]).astype(int)
    frame["2H goal"] = ((frame["2H home goals"] + frame["2H away goals"]) > 0).astype(int)
    frame["2H over 1.5"] = ((frame["2H home goals"] + frame["2H away goals"]) >= 2).astype(int)
    frame["Home FT win"] = (frame.home_goals > frame.away_goals).astype(int)
    frame["Away FT win"] = (frame.away_goals > frame.home_goals).astype(int)
    frame["FT draw"] = (frame.home_goals == frame.away_goals).astype(int)
    frame["HT xG leader"] = "Unavailable"
    valid_xg = frame.home_ht_xg.notna() & frame.away_ht_xg.notna()
    frame.loc[valid_xg, "HT xG leader"] = "Equal"
    frame.loc[valid_xg & (frame.home_ht_xg > frame.away_ht_xg), "HT xG leader"] = "Home"
    frame.loc[valid_xg & (frame.home_ht_xg < frame.away_ht_xg), "HT xG leader"] = "Away"
    return frame

with tab4:
    st.subheader("Historical halftime pattern explorer")
    st.caption("Descriptive frequencies from existing StatsAPI match scores; NOT betting profitability or model prices.")
    if st.button("Load stored halftime outcomes", type="primary"):
        try:
            frame = halftime_research_data()
            st.session_state["ht_research_loaded"] = not frame.empty
        except Exception as exc:
            st.session_state["ht_research_loaded"] = False
            st.error(f"Historical research unavailable: {type(exc).__name__}: {exc}")
    if st.session_state.get("ht_research_loaded"):
        frame = halftime_research_data()
        leagues = st.multiselect("League", sorted(frame["League"].unique()),
                                 default=sorted(frame["League"].unique()), key="ht_leagues")
        states = st.multiselect("Halftime score situation",
                                ["Draw", "Home leading", "Away leading"],
                                default=["Draw", "Home leading", "Away leading"])
        xg_leaders = st.multiselect("Half-time xG leader",
                                    ["Home", "Away", "Equal", "Unavailable"],
                                    default=["Home", "Away", "Equal", "Unavailable"])
        filtered = frame[frame["League"].isin(leagues) &
                         frame["HT state"].isin(states) &
                         frame["HT xG leader"].isin(xg_leaders)].copy()
        st.metric("Qualifying historical matches", f"{len(filtered):,}")
        if not filtered.empty:
            outcomes = {
                "Home scored in both halves": "Both halves home scored",
                "Away scored in both halves": "Both halves away scored",
                "Home won both halves": "Home won both halves",
                "Away won both halves": "Away won both halves",
                "Second half draw": "2H draw",
                "At least one second-half goal": "2H goal",
                "At least two second-half goals": "2H over 1.5",
                "Home full-time win": "Home FT win",
                "Away full-time win": "Away FT win",
                "Full-time draw": "FT draw",
            }
            result = pd.DataFrame([
                {"Outcome": label, "Matches": len(filtered),
                 "Hits": int(filtered[col].sum()),
                 "Hit rate %": round(100 * filtered[col].mean(), 2)}
                for label, col in outcomes.items()
            ])
            st.dataframe(result, use_container_width=True, hide_index=True)
            st.download_button("Export filtered results", result.to_csv(index=False),
                               "starlizard_halftime_patterns.csv", "text/csv")
            st.caption("All results are in-sample descriptive counts; no market odds, EV or ROI is inferred.")

with tab5:
    st.subheader("Chronological out-of-sample baseline")
    st.caption("Training matches precede testing matches. A whole match date stays on one side of the split.")
    fraction = st.slider("Training fraction", 0.50, 0.85, 0.70, 0.05)
    min_train = st.number_input("Minimum training matches per league", 30, 500, 100, 10)
    metric = st.selectbox("Historical outcome", [
        "2H goal", "2H over 1.5", "2H draw", "Home FT win",
        "Away FT win", "FT draw", "Home won both halves",
        "Away won both halves", "Both halves home scored", "Both halves away scored",
    ])
    if st.button("Run holdout evaluation", type="primary"):
        try:
            frame = halftime_research_data()
            records = []
            for league, group in frame.groupby("League"):
                rows = group[["match_id", "match_date", metric]].dropna().copy()
                rows["match_date"] = pd.to_datetime(rows["match_date"], errors="coerce").dt.strftime("%Y-%m-%d")
                rows = rows.dropna()
                if len(rows) < 2:
                    continue
                train, test, split_date = chronological_split(rows.to_dict("records"), fraction)
                result = evaluate_binary_baseline(train, test, metric, int(min_train))
                if result is None:
                    continue
                records.append({
                    "League": league,
                    "Test from": split_date,
                    "Train n": result["train_n"],
                    "Test n": result["test_n"],
                    "Train rate %": round(100*result["train_rate"], 2),
                    "Test rate %": round(100*result["test_rate"], 2),
                    "Test Brier": round(result["test_brier"], 4),
                    "Test uncertainty low %": round(100*result["test_wilson_low"], 2),
                    "Test uncertainty high %": round(100*result["test_wilson_high"], 2),
                })
            if records:
                report = pd.DataFrame(records).sort_values("Test n", ascending=False)
                st.dataframe(report, use_container_width=True, hide_index=True)
                st.download_button("Export holdout report", report.to_csv(index=False),
                                   "starlizard_holdout_baseline.csv", "text/csv")
            else:
                st.warning("No leagues passed the minimum sample requirements.")
        except Exception as exc:
            st.error(f"Holdout evaluation failed: {type(exc).__name__}: {exc}")
    st.warning("Baseline only: it does not use time-aligned bookmaker quotes and cannot establish a profitable edge.")

@st.cache_data(ttl=900)
def bookmaker_odds_quality():
    """Counts usable Bet365 1X2 quotes; no provider calls or odds timestamp assumptions."""
    results = {}
    for offset in range(0, 100000, 1000):
        batch = (db().table("historical_match_odds")
                 .select("match_id,odds_payload")
                 .order("match_id").range(offset, offset+999).execute().data or [])
        for row in batch:
            payload = row.get("odds_payload") or {}
            books = (payload.get("data") or {}).get("bookmakers") or []
            book = next((b for b in books if b.get("bookmaker") == "Bet365"), None)
            if book is None:
                continue
            market = (book.get("markets") or {}).get("match_odds") or {}
            def valid(side, field):
                try:
                    quote = float((market.get(side) or {}).get(field))
                    return 1.01 <= quote <= 1000
                except (ValueError, TypeError):
                    return False
            results[str(row["match_id"])] = {
                "Bet365": 1,
                "Complete opening 1X2": int(all(valid(s, "opening") for s in ("home", "draw", "away"))),
                "Complete last-seen 1X2": int(all(valid(s, "last_seen") for s in ("home", "draw", "away"))),
            }
        if len(batch) < 1000:
            break
    return results

@st.cache_data(ttl=900)
def odds_quality_by_league():
    quotes = bookmaker_odds_quality()
    rows = []
    for offset in range(0, 100000, 1000):
        batch = (db().table("historical_xg").select("match_id,competition_id")
                 .order("match_id").range(offset, offset+999).execute().data or [])
        for match in batch:
            stats = quotes.get(str(match["match_id"]), {})
            rows.append({
                "League": LEAGUE_NAMES.get(match.get("competition_id"), "Unassigned"),
                "Match ID": str(match["match_id"]),
                "Bet365": stats.get("Bet365", 0),
                "Complete opening 1X2": stats.get("Complete opening 1X2", 0),
                "Complete last-seen 1X2": stats.get("Complete last-seen 1X2", 0),
            })
        if len(batch) < 1000:
            break
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows).drop_duplicates("Match ID")
    return (frame.groupby("League", as_index=False)
            .agg(Matches=("Match ID", "count"),
                 Bet365=("Bet365", "sum"),
                 Complete_opening_1X2=("Complete opening 1X2", "sum"),
                 Complete_last_seen_1X2=("Complete last-seen 1X2", "sum"))
            .sort_values("Matches", ascending=False))

with tab6:
    st.subheader("Historical bookmaker quote completeness")
    st.caption("Presence of all three 1X2 quotes, not proof of when the quote was offered.")
    if st.button("Audit stored Bet365 odds", type="primary"):
        try:
            report = odds_quality_by_league()
            st.session_state["odds_quality_report"] = report
        except Exception as exc:
            st.error(f"Odds quality audit failed: {type(exc).__name__}: {exc}")
    if "odds_quality_report" in st.session_state:
        report = st.session_state["odds_quality_report"]
        st.dataframe(report, use_container_width=True, hide_index=True)
        st.download_button("Export odds quality report", report.to_csv(index=False),
                           "starlizard_odds_quality.csv", "text/csv")
    st.warning("Last-seen prices are not verified pre-match closing odds. Neither opening nor last-seen quotes are time-aligned in-play prices. Do not calculate in-play ROI from them.")

with tab7:
    st.subheader("Automatic halftime pattern discovery — research only")
    st.caption("Searches combinations of leagues, halftime state and xG advantage. Uses separate historical training and later test matches.")
    outcome = st.selectbox("Outcome to investigate", [
        "2H goal", "2H over 1.5", "2H draw", "Home FT win",
        "Away FT win", "FT draw", "Home won both halves",
        "Away won both halves", "Both halves home scored", "Both halves away scored",
    ], key="discover_outcome")
    min_samples = st.slider("Minimum training matches per pattern", 100, 500, 200, 50)
    min_test = st.slider("Minimum held-out matches per pattern", 30, 150, 50, 10)
    if st.button("Search for stable patterns", type="primary"):
        try:
            frame = halftime_research_data().copy()
            frame["match_date"] = pd.to_datetime(frame["match_date"], errors="coerce")
            frame = frame.dropna(subset=["match_date", outcome])
            # Global calendar split, not a separate post-hoc split for each candidate.
            calendar = frame[["match_id", "match_date"]].copy()
            calendar["match_date"] = calendar["match_date"].dt.strftime("%Y-%m-%d")
            training, testing, cutoff = chronological_split(calendar.to_dict("records"), .70)
            training_ids = {r["match_id"] for r in training}
            testing_ids = {r["match_id"] for r in testing}
            train = frame[frame.match_id.isin(training_ids)]
            test = frame[frame.match_id.isin(testing_ids)]
            base_rate = train[outcome].mean()
            discoveries = []
            for league in sorted(frame["League"].unique()):
                for state in ("Draw", "Home leading", "Away leading"):
                    for xg in ("Home", "Away", "Equal"):
                        tr = train[(train["League"] == league) &
                                   (train["HT state"] == state) &
                                   (train["HT xG leader"] == xg)]
                        te = test[(test["League"] == league) &
                                  (test["HT state"] == state) &
                                  (test["HT xG leader"] == xg)]
                        if len(tr) < min_samples or len(te) < min_test:
                            continue
                        training_rate = tr[outcome].mean()
                        testing_rate = te[outcome].mean()
                        lo, hi = wilson_interval(int(te[outcome].sum()), len(te))
                        discoveries.append({
                            "League": league, "HT state": state, "HT xG leader": xg,
                            "Train n": len(tr), "Test n": len(te),
                            "Train rate %": round(100*training_rate, 2),
                            "Test rate %": round(100*testing_rate, 2),
                            "Test low %": round(100*lo, 2),
                            "Test high %": round(100*hi, 2),
                            "Train vs overall pp": round(100*(training_rate-base_rate), 2),
                            "Direction held": bool((training_rate-base_rate)*(testing_rate-base_rate) > 0),
                        })
            st.caption(f"All candidate definitions evaluated against the same global test cutoff: {cutoff}.")
            if discoveries:
                result = pd.DataFrame(discoveries).sort_values(
                    ["Direction held", "Test n"], ascending=[False, False])
                st.dataframe(result, use_container_width=True, hide_index=True)
                st.download_button("Export pattern search", result.to_csv(index=False),
                                   "starlizard_pattern_search.csv", "text/csv")
            else:
                st.warning("No candidates met both sample-size thresholds.")
        except Exception as exc:
            st.error(f"Pattern search failed: {type(exc).__name__}: {exc}")
    st.warning("Exploratory screen, not a betting signal. Testing many candidates creates selection bias; promising results need an untouched second validation period and real time-aligned market quotes.")
