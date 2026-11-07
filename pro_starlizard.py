
import streamlit as st
import pandas as pd
from datetime import date
from supabase import create_client

st.set_page_config(
    page_title="PRO STARLIZARD",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
.stApp {
    background-color: #0b1220;
    color: #e8eef8;
}
.block-container {
    padding-top: .5rem;
    padding-bottom: 2rem;
    max-width: 1100px;
}
h1, h2, h3 {
    color: #f8fafc !important;
}
label,
[data-testid="stWidgetLabel"],
[data-testid="stWidgetLabel"] p {
    color: #e8eef8 !important;
    font-weight: 600 !important;
}
div[data-testid="stMetric"] {
    background: #172338;
    border: 1px solid #293a53;
    border-radius: 12px;
    padding: 12px;
}
div[data-testid="stMetricValue"],
div[data-testid="stMetricValue"] *,
div[data-testid="stMetricLabel"],
div[data-testid="stMetricLabel"] * {
    color: #f8fafc !important;
    opacity: 1 !important;
}
div.stButton > button {
    width: 100%;
    min-height: 3.2rem;
    border-radius: 12px;
    font-size: 1rem;
    font-weight: 700;
    border: 1px solid #41536c;
}
div.stButton > button[kind="primary"] {
    background-color: #b91c38;
    border-color: #ef4766;
    color: white;
}
div.stButton > button[kind="secondary"] {
    background-color: #172338;
    color: #f8fafc;
}
div.stButton > button p {
    color: inherit !important;
}
@media(max-width:640px) {
    .block-container {
        padding-left: 1rem;
        padding-right: 1rem;
    }
    h1 {
        font-size: 1.8rem !important;
    }
    h2 {
        font-size: 1.4rem !important;
    }
}
</style>
""", unsafe_allow_html=True)

st.image(
    "pro_starlizard_header_correct-1.png",
    width="stretch",
)

# Verified domestic league competition IDs.
# Cup and European competition records are excluded
# from Historical Research.
LEAGUES = {
    "comp_0256": "France - Ligue 1",
    "comp_3039": "England - Premier League",
    "comp_3809": "Netherlands - Eredivisie",
    "comp_4643": "Germany - Bundesliga",
    "comp_5840": "Italy - Serie A",
    "comp_6387": "Scotland - Premiership",
    "comp_8321": "England - Championship",
    "comp_8385": "Portugal - Primeira Liga",
    "comp_8531": "Belgium - Pro League",
    "comp_8814": "Spain - La Liga",
}

LEAGUE_IDS = list(LEAGUES.keys())


@st.cache_resource
def get_supabase():
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_SECRET_KEY"],
    )


@st.cache_data(ttl=120, show_spinner=False)
def get_database_stats():
    db = get_supabase()

    checks = [
        (
            "Historical xG records",
            "historical_xg",
            None,
            None,
        ),
        (
            "Match event records collected",
            "historical_match_events",
            None,
            None,
        ),
        (
            "Match statistics received",
            "historical_match_events",
            "stats_status",
            200,
        ),
        (
            "Goal/event timelines received",
            "historical_match_events",
            "timeline_status",
            200,
        ),
        (
            "Corners matched",
            "historical_match_events",
            "corners_match",
            True,
        ),
        (
            "Yellow cards matched",
            "historical_match_events",
            "yellow_cards_match",
            True,
        ),
        (
            "Red cards matched",
            "historical_match_events",
            "red_cards_match",
            True,
        ),
    ]

    results = {}
    errors = {}

    for label, table, column, value in checks:
        try:
            query = db.table(table).select(
                "match_id",
                count="exact",
            )

            if column is not None:
                query = query.eq(column, value)

            response = query.limit(1).execute()
            results[label] = response.count

        except Exception as exc:
            results[label] = None
            errors[label] = type(exc).__name__

    return results, errors


@st.cache_data(ttl=3600, show_spinner=False)
def find_team_names(fragment):
    db = get_supabase()
    found = set()

    # Search only domestic league records.
    for field in ("home_team", "away_team"):
        response = (
            db.table("historical_xg")
            .select(field)
            .in_("competition_id", LEAGUE_IDS)
            .ilike(field, "%" + fragment + "%")
            .limit(200)
            .execute()
        )

        for row in response.data or []:
            name = row.get(field)
            if name:
                found.add(name)

    return sorted(found, key=str.casefold)


@st.cache_data(ttl=300, show_spinner=False)
def get_team_league_matches(team, sample, as_of_date):
    db = get_supabase()

    fields = (
        "match_id,competition_id,match_date,"
        "home_team,away_team,"
        "home_goals,away_goals,"
        "home_ht_goals,away_ht_goals,"
        "home_xg,away_xg,"
        "home_ht_xg,away_ht_xg"
    )

    # Fetch more than the requested sample to allow
    # for home/away mixing and data validation.
    fetch_limit = max(150, sample * 4)

    rows = []

    for team_field in ("home_team", "away_team"):
        response = (
            db.table("historical_xg")
            .select(fields)
            .eq(team_field, team)
            .in_("competition_id", LEAGUE_IDS)
            .lte("match_date", as_of_date)
            .order("match_date", desc=True)
            .limit(fetch_limit)
            .execute()
        )

        rows.extend(response.data or [])

    # Deduplicate by match ID.
    unique = {}

    for row in rows:
        match_id = row.get("match_id")

        if match_id is not None:
            unique[str(match_id)] = row

    ordered = sorted(
        unique.values(),
        key=lambda row: (
            row.get("match_date") or "",
            str(row.get("match_id") or ""),
        ),
        reverse=True,
    )

    selected = []
    incomplete = []

    for row in ordered:
        if len(selected) >= sample:
            break

        # Never silently treat a missing score as 0.
        if (
            row.get("home_goals") is None
            or row.get("away_goals") is None
        ):
            incomplete.append(row)
            continue

        selected.append(row)

    return selected, incomplete


def number(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def show_team_analysis(team, matches, incomplete, sample):
    if not matches:
        st.warning(
            "No completed domestic league matches found "
            "for this team and date."
        )
        return

    data = []

    for row in matches:
        is_home = row.get("home_team") == team

        gf = (
            row.get("home_goals")
            if is_home
            else row.get("away_goals")
        )

        ga = (
            row.get("away_goals")
            if is_home
            else row.get("home_goals")
        )

        ht_gf = (
            row.get("home_ht_goals")
            if is_home
            else row.get("away_ht_goals")
        )

        ht_ga = (
            row.get("away_ht_goals")
            if is_home
            else row.get("home_ht_goals")
        )

        xgf = number(
            row.get("home_xg")
            if is_home
            else row.get("away_xg")
        )

        xga = number(
            row.get("away_xg")
            if is_home
            else row.get("home_xg")
        )

        ht_xgf = number(
            row.get("home_ht_xg")
            if is_home
            else row.get("away_ht_xg")
        )

        ht_xga = number(
            row.get("away_ht_xg")
            if is_home
            else row.get("home_ht_xg")
        )

        gf_number = number(gf)
        ga_number = number(ga)

        if gf_number is None or ga_number is None:
            result = "—"
        elif gf_number > ga_number:
            result = "W"
        elif gf_number == ga_number:
            result = "D"
        else:
            result = "L"

        competition_id = row.get("competition_id")

        data.append({
            "Date": row.get("match_date"),
            "League": LEAGUES.get(
                competition_id,
                "Unknown league",
            ),
            "Venue": "Home" if is_home else "Away",
            "Opponent": (
                row.get("away_team")
                if is_home
                else row.get("home_team")
            ),
            "GF": gf,
            "GA": ga,
            "HT GF": ht_gf,
            "HT GA": ht_ga,
            "xGF": xgf,
            "xGA": xga,
            "HT xGF": ht_xgf,
            "HT xGA": ht_xga,
            "Result": result,
        })

    df = pd.DataFrame(data)

    st.success(
        f"{len(df)} completed domestic league matches "
        f"loaded for {team}."
    )

    if len(df) < sample:
        st.warning(
            f"You requested {sample} league matches, "
            f"but only {len(df)} completed matches "
            "were found in the available history."
        )

    if incomplete:
        st.warning(
            f"{len(incomplete)} league records with "
            "missing full-time scores were skipped. "
            "These should be investigated."
        )

    league_names = sorted(df["League"].dropna().unique())

    st.caption(
        "Competition coverage: " + ", ".join(league_names)
    )

    st.subheader("Recent league performance")

    scored = df[df["Result"].isin(["W", "D", "L"])]

    wins = int((scored["Result"] == "W").sum())
    draws = int((scored["Result"] == "D").sum())
    losses = int((scored["Result"] == "L").sum())

    c1, c2, c3 = st.columns(3)

    c1.metric("Wins", wins)
    c2.metric("Draws", draws)
    c3.metric("Losses", losses)

    st.caption(
        "All results use domestic league fixtures only. "
        "Each average uses the number of matches "
        "with that statistic available."
    )

    def metric_summary(frame, title):
        st.markdown(
            f"**{title} — {len(frame)} league matches**"
        )

        if frame.empty:
            st.info("No matches in this split.")
            return

        metrics = [
            ("Goals scored", "GF"),
            ("Goals conceded", "GA"),
            ("xG for", "xGF"),
            ("xG against", "xGA"),
            ("HT goals for", "HT GF"),
            ("HT goals against", "HT GA"),
            ("HT xG for", "HT xGF"),
            ("HT xG against", "HT xGA"),
        ]

        for label, column in metrics:
            values = pd.to_numeric(
                frame[column],
                errors="coerce",
            ).dropna()

            if not values.empty:
                st.metric(
                    f"{label} ({len(values)} matches)",
                    f"{values.mean():.2f}",
                )

    tab1, tab2, tab3 = st.tabs([
        "All league matches",
        "Home",
        "Away",
    ])

    with tab1:
        metric_summary(df, "All")

    with tab2:
        metric_summary(
            df[df["Venue"] == "Home"],
            "Home",
        )

    with tab3:
        metric_summary(
            df[df["Venue"] == "Away"],
            "Away",
        )

    st.subheader("Match-by-match league results")

    st.dataframe(
        df,
        hide_index=True,
        width="stretch",
    )

    if incomplete:
        with st.expander(
            "Inspect incomplete league records"
        ):
            audit_rows = []

            for row in incomplete:
                audit_rows.append({
                    "Date": row.get("match_date"),
                    "Home": row.get("home_team"),
                    "Away": row.get("away_team"),
                    "Competition ID": row.get(
                        "competition_id"
                    ),
                    "Match ID": row.get("match_id"),
                })

            st.dataframe(
                pd.DataFrame(audit_rows),
                hide_index=True,
                width="stretch",
            )

    st.caption(
        "Only the ten identified domestic leagues "
        "are included. Cup and European fixtures "
        "are excluded. This is historical research, "
        "not a verified betting edge."
    )


if "active_page" not in st.session_state:
    st.session_state.active_page = "Match Pricing"

for page, icon in [
    ("Match Pricing", "⚽"),
    ("Historical Research", "📊"),
    ("Database Health", "🗄️"),
]:
    selected_page = (
        st.session_state.active_page == page
    )

    if st.button(
        f"{icon}  {page}",
        key=f"nav_{page}",
        width="stretch",
        type=(
            "primary"
            if selected_page
            else "secondary"
        ),
    ):
        st.session_state.active_page = page
        st.rerun()

st.divider()


if st.session_state.active_page == "Match Pricing":
    st.header("Match Pricing")

    st.caption(
        "Pre-match and in-play football pricing terminal"
    )

    st.text_input(
        "Home team",
        placeholder="Enter home team",
    )

    st.text_input(
        "Away team",
        placeholder="Enter away team",
    )

    st.selectbox(
        "Select market",
        [
            "Match Goals",
            "Second-Half Goals",
            "Match Corners",
            "Second-Half Corners",
            "Cards",
            "Asian Handicap",
            "Asian Goal Totals",
            "Correct Score",
            "Next Goal",
            "Both Teams To Score",
        ],
    )

    st.info(
        "Pricing engine not connected yet. "
        "This is our dashboard preview."
    )


elif st.session_state.active_page == "Historical Research":
    st.header("Historical Research")

    st.caption(
        "Domestic league matches only — "
        "historical data from Supabase. "
        "No StatsAPI calls."
    )

    st.info(
        "League-only research is enabled. "
        "Cup and European matches are excluded."
    )

    fragment = st.text_input(
        "Find a team",
        placeholder="e.g. Newcastle",
        max_chars=60,
    ).strip()

    if fragment:
        if len(fragment) < 3:
            st.info(
                "Type at least three letters "
                "to search for a team."
            )

        elif "%" in fragment or "_" in fragment:
            st.warning(
                "Please use ordinary team-name "
                "letters rather than % or _."
            )

        else:
            try:
                teams = find_team_names(fragment)

                if not teams:
                    st.warning(
                        "No matching league team found. "
                        "Try another spelling."
                    )

                else:
                    team = st.selectbox(
                        "Choose team",
                        teams,
                    )

                    sample = st.select_slider(
                        "Recent league matches",
                        options=[
                            5, 10, 15, 20, 30, 50
                        ],
                        value=20,
                    )

                    as_of = st.date_input(
                        "Include matches up to",
                        value=date.today(),
                        max_value=date.today(),
                    )

                    if st.button(
                        "📊 Analyse league form",
                        type="primary",
                        width="stretch",
                    ):
                        st.session_state[
                            "research_selection"
                        ] = (
                            team,
                            sample,
                            as_of.isoformat(),
                        )

                    selection = st.session_state.get(
                        "research_selection"
                    )

                    current_selection = (
                        team,
                        sample,
                        as_of.isoformat(),
                    )

                    if selection == current_selection:
                        with st.spinner(
                            "Loading league matches..."
                        ):
                            matches, incomplete = (
                                get_team_league_matches(
                                    team,
                                    sample,
                                    as_of.isoformat(),
                                )
                            )

                        show_team_analysis(
                            team,
                            matches,
                            incomplete,
                            sample,
                        )

            except Exception as exc:
                st.error(
                    "Research request failed "
                    f"({type(exc).__name__}). "
                    "No data has been changed."
                )

    st.caption(
        "Corners, cards and goal timings will "
        "follow after event-data joins and "
        "verification filters are implemented."
    )


elif st.session_state.active_page == "Database Health":
    st.header("Database Health")

    st.caption(
        "Live historical collection statistics "
        "from Supabase"
    )

    if st.button(
        "🔄 Refresh database figures",
        width="stretch",
    ):
        get_database_stats.clear()

    try:
        with st.spinner(
            "Checking database tables..."
        ):
            results, errors = get_database_stats()

        passed = sum(
            value is not None
            for value in results.values()
        )

        if passed == 7:
            st.success(
                "All seven database checks succeeded."
            )
        else:
            st.warning(
                f"{passed} of 7 database checks succeeded."
            )

        groups = [
            (
                "Historical Database",
                [
                    "Historical xG records",
                    "Match event records collected",
                ],
            ),
            (
                "Collection Status",
                [
                    "Match statistics received",
                    "Goal/event timelines received",
                ],
            ),
            (
                "Verified Markets",
                [
                    "Corners matched",
                    "Yellow cards matched",
                    "Red cards matched",
                ],
            ),
        ]

        for heading, labels in groups:
            st.subheader(heading)

            for label in labels:
                value = results.get(label)

                st.metric(
                    label,
                    (
                        f"{value:,}"
                        if value is not None
                        else "Unavailable"
                    ),
                )

        total = results.get(
            "Match event records collected"
        )

        verified = results.get(
            "Corners matched"
        )

        if total and verified is not None:
            st.metric(
                "Corner verification rate",
                f"{100 * verified / total:.1f}%",
            )

        st.subheader("Database Diagnostics")

        if errors:
            for label, kind in errors.items():
                st.error(
                    f"{label}: {kind}"
                )
        else:
            st.success(
                "No database query errors detected."
            )

        st.caption(
            "Read-only queries. Figures are cached "
            "for two minutes. Received timelines "
            "are not independently goal-verified "
            "by this dashboard."
        )

    except Exception as exc:
        st.error(
            "Database connection failed "
            f"({type(exc).__name__})."
        )


st.divider()

st.caption(
    "PRO STARLIZARD | Research and model "
    "estimates only. No automated betting."
)

st.caption(
    "🦎 Scrumpy & Lady Sally — "
    "Data Acquisition Team"
)
