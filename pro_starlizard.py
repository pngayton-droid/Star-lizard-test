
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

# --------------------------------------------------
# APPEARANCE
# --------------------------------------------------

st.markdown("""
<style>
.stApp {
    background-color: #0b1220;
    color: #e8eef8;
}

.block-container {
    padding-top: 4.5rem !important;
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

[data-testid="stImage"] img {
    object-fit: contain !important;
    height: auto !important;
}

@media (max-width: 640px) {
    .block-container {
        padding-top: 4rem !important;
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

# --------------------------------------------------
# DOMESTIC LEAGUES
# --------------------------------------------------

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

FIELDS = (
    "match_id,competition_id,match_date,"
    "home_team,away_team,"
    "home_goals,away_goals,"
    "home_ht_goals,away_ht_goals,"
    "home_xg,away_xg,"
    "home_ht_xg,away_ht_xg"
)

METRICS = [
    ("Goals scored", "GF"),
    ("Goals conceded", "GA"),
    ("xG for", "xGF"),
    ("xG against", "xGA"),
    ("HT goals scored", "HT GF"),
    ("HT goals conceded", "HT GA"),
    ("HT xG for", "HT xGF"),
    ("HT xG against", "HT xGA"),
]

# --------------------------------------------------
# SUPABASE
# --------------------------------------------------

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


def numeric(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def has_score(row):
    return (
        numeric(row.get("home_goals")) is not None
        and numeric(row.get("away_goals")) is not None
    )


# --------------------------------------------------
# HISTORICAL DATA FETCHING
# --------------------------------------------------

@st.cache_data(ttl=300, show_spinner=False)
def get_matches(
    team,
    count,
    as_of,
    venue="All",
):
    db = get_supabase()
    records = []

    if venue == "Home":
        fields_to_search = ["home_team"]
    elif venue == "Away":
        fields_to_search = ["away_team"]
    else:
        fields_to_search = [
            "home_team",
            "away_team",
        ]

    # We fetch a larger window than requested
    # so the last 20 overall are genuinely
    # the last 20, regardless of venue.
    fetch_limit = max(150, count * 4)

    for team_field in fields_to_search:
        response = (
            db.table("historical_xg")
            .select(FIELDS)
            .eq(team_field, team)
            .in_("competition_id", LEAGUE_IDS)
            .lte("match_date", as_of)
            .order("match_date", desc=True)
            .limit(fetch_limit)
            .execute()
        )

        records.extend(response.data or [])

    unique = {}

    for row in records:
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

    completed = []
    incomplete = []

    for row in ordered:
        if len(completed) >= count:
            break

        if has_score(row):
            completed.append(row)
        else:
            incomplete.append(row)

    return completed, incomplete


# --------------------------------------------------
# MATCH DATAFRAME
# --------------------------------------------------

def build_dataframe(team, matches):
    columns = [
        "Date",
        "League",
        "Venue",
        "Opponent",
        "GF",
        "GA",
        "HT GF",
        "HT GA",
        "xGF",
        "xGA",
        "HT xGF",
        "HT xGA",
        "Result",
    ]

    rows = []

    for match in matches:
        home = match.get("home_team") == team

        gf = numeric(
            match.get("home_goals")
            if home else match.get("away_goals")
        )

        ga = numeric(
            match.get("away_goals")
            if home else match.get("home_goals")
        )

        ht_gf = numeric(
            match.get("home_ht_goals")
            if home else match.get("away_ht_goals")
        )

        ht_ga = numeric(
            match.get("away_ht_goals")
            if home else match.get("home_ht_goals")
        )

        xgf = numeric(
            match.get("home_xg")
            if home else match.get("away_xg")
        )

        xga = numeric(
            match.get("away_xg")
            if home else match.get("home_xg")
        )

        ht_xgf = numeric(
            match.get("home_ht_xg")
            if home else match.get("away_ht_xg")
        )

        ht_xga = numeric(
            match.get("away_ht_xg")
            if home else match.get("home_ht_xg")
        )

        if gf is None or ga is None:
            result = "—"
        elif gf > ga:
            result = "W"
        elif gf < ga:
            result = "L"
        else:
            result = "D"

        rows.append({
            "Date": match.get("match_date"),
            "League": LEAGUES.get(
                match.get("competition_id"),
                "Unknown",
            ),
            "Venue": "Home" if home else "Away",
            "Opponent": (
                match.get("away_team")
                if home else match.get("home_team")
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

    return pd.DataFrame(rows, columns=columns)


def average(df, column):
    if df.empty:
        return None

    values = pd.to_numeric(
        df[column],
        errors="coerce",
    ).dropna()

    if values.empty:
        return None

    return float(values.mean())


def fmt(value):
    if value is None:
        return "—"

    return f"{value:.2f}"


def record_text(df):
    if df.empty:
        return "No matches"

    wins = int((df["Result"] == "W").sum())
    draws = int((df["Result"] == "D").sum())
    losses = int((df["Result"] == "L").sum())

    return f"{wins}W / {draws}D / {losses}L"


# --------------------------------------------------
# TWO-TEAM COMPARISON
# --------------------------------------------------

def comparison_table(
    home_name,
    away_name,
    home_df,
    away_df,
):
    rows = []

    for label, column in METRICS:
        home_values = pd.to_numeric(
            home_df[column],
            errors="coerce",
        ).dropna()

        away_values = pd.to_numeric(
            away_df[column],
            errors="coerce",
        ).dropna()

        rows.append({
            "Statistic": label,
            "Home team": (
                f"{home_values.mean():.2f}"
                f" (n={len(home_values)})"
                if not home_values.empty
                else "—"
            ),
            "Away team": (
                f"{away_values.mean():.2f}"
                f" (n={len(away_values)})"
                if not away_values.empty
                else "—"
            ),
        })

    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        width="stretch",
        column_config={
            "Statistic": st.column_config.TextColumn(
                "Statistic"
            ),
            "Home team": st.column_config.TextColumn(
                home_name
            ),
            "Away team": st.column_config.TextColumn(
                away_name
            ),
        },
    )


def show_comparison(
    home_team,
    away_team,
    overall_count,
    venue_count,
    as_of,
):
    if home_team == away_team:
        st.warning(
            "Choose two different teams."
        )
        return

    with st.spinner(
        "Loading historical league records..."
    ):
        home_all, home_all_missing = get_matches(
            home_team,
            overall_count,
            as_of,
            "All",
        )

        away_all, away_all_missing = get_matches(
            away_team,
            overall_count,
            as_of,
            "All",
        )

        home_venue, home_venue_missing = get_matches(
            home_team,
            venue_count,
            as_of,
            "Home",
        )

        away_venue, away_venue_missing = get_matches(
            away_team,
            venue_count,
            as_of,
            "Away",
        )

    home_all_df = build_dataframe(
        home_team, home_all
    )
    away_all_df = build_dataframe(
        away_team, away_all
    )

    home_venue_df = build_dataframe(
        home_team, home_venue
    )
    away_venue_df = build_dataframe(
        away_team, away_venue
    )

    st.success(
        "Domestic league comparison loaded."
    )

    st.caption(
        "All samples use recorded domestic league "
        "competition IDs only. Cup and European "
        "fixtures are excluded."
    )

    # ----------------------------------------------
    # OVERALL FORM
    # ----------------------------------------------

    st.header("Overall league form")

    st.caption(
        f"Last {overall_count} league matches "
        "per team, home and away combined."
    )

    c1, c2 = st.columns(2)

    with c1:
        st.markdown(f"**HOME: {home_team}**")
        st.metric(
            "Matches",
            len(home_all_df),
        )
        st.write(record_text(home_all_df))

    with c2:
        st.markdown(f"**AWAY: {away_team}**")
        st.metric(
            "Matches",
            len(away_all_df),
        )
        st.write(record_text(away_all_df))

    comparison_table(
        home_team,
        away_team,
        home_all_df,
        away_all_df,
    )

    # ----------------------------------------------
    # VENUE FORM
    # ----------------------------------------------

    st.header("Home versus away form")

    st.caption(
        f"Last {venue_count} home league matches "
        f"for {home_team}, compared with the "
        f"last {venue_count} away league matches "
        f"for {away_team}."
    )

    c1, c2 = st.columns(2)

    with c1:
        st.markdown(
            f"**{home_team} — HOME**"
        )
        st.metric(
            "Home matches",
            len(home_venue_df),
        )
        st.write(
            record_text(home_venue_df)
        )

    with c2:
        st.markdown(
            f"**{away_team} — AWAY**"
        )
        st.metric(
            "Away matches",
            len(away_venue_df),
        )
        st.write(
            record_text(away_venue_df)
        )

    comparison_table(
        home_team,
        away_team,
        home_venue_df,
        away_venue_df,
    )

    # ----------------------------------------------
    # ATTACK VERSUS DEFENCE
    # ----------------------------------------------

    st.header("Attack versus defence")

    st.caption(
        "Compare each team's attacking output "
        "with the opposition's defensive record. "
        "These are historical averages, not "
        "opposition-adjusted predictions."
    )

    attack_rows = [
        {
            "Comparison": (
                f"{home_team} attack"
            ),
            "Attacking xG": fmt(
                average(home_venue_df, "xGF")
            ),
            "Opponent xG conceded": fmt(
                average(away_venue_df, "xGA")
            ),
        },
        {
            "Comparison": (
                f"{away_team} attack"
            ),
            "Attacking xG": fmt(
                average(away_venue_df, "xGF")
            ),
            "Opponent xG conceded": fmt(
                average(home_venue_df, "xGA")
            ),
        },
    ]

    st.dataframe(
        pd.DataFrame(attack_rows),
        hide_index=True,
        width="stretch",
    )

    # ----------------------------------------------
    # MATCH-BY-MATCH DATA
    # ----------------------------------------------

    st.header("Match-by-match records")

    with st.expander(
        f"{home_team} — overall league matches"
    ):
        st.dataframe(
            home_all_df,
            hide_index=True,
            width="stretch",
        )

    with st.expander(
        f"{away_team} — overall league matches"
    ):
        st.dataframe(
            away_all_df,
            hide_index=True,
            width="stretch",
        )

    with st.expander(
        f"{home_team} — home league matches"
    ):
        st.dataframe(
            home_venue_df,
            hide_index=True,
            width="stretch",
        )

    with st.expander(
        f"{away_team} — away league matches"
    ):
        st.dataframe(
            away_venue_df,
            hide_index=True,
            width="stretch",
        )

    # ----------------------------------------------
    # DATA QUALITY
    # ----------------------------------------------

    st.header("Data quality")

    samples = [
        (
            home_team + " overall",
            len(home_all_df),
            overall_count,
            len(home_all_missing),
        ),
        (
            away_team + " overall",
            len(away_all_df),
            overall_count,
            len(away_all_missing),
        ),
        (
            home_team + " home",
            len(home_venue_df),
            venue_count,
            len(home_venue_missing),
        ),
        (
            away_team + " away",
            len(away_venue_df),
            venue_count,
            len(away_venue_missing),
        ),
    ]

    issues = False

    for label, found, requested, missing in samples:
        if found < requested:
            issues = True
            st.warning(
                f"{label}: {found}/{requested} "
                "completed league matches available."
            )

        if missing:
            issues = True
            st.warning(
                f"{label}: {missing} league records "
                "with missing scores encountered."
            )

    if not issues:
        st.success(
            "All four requested samples are "
            "complete, with no missing-score "
            "league records encountered."
        )

    st.caption(
        "Averages use only available values. "
        "The comparison does not yet adjust "
        "for opponent strength, fixture dates "
        "or changes in team personnel."
    )


# --------------------------------------------------
# NAVIGATION
# --------------------------------------------------

if "active_page" not in st.session_state:
    st.session_state.active_page = "Match Pricing"

for page, icon in [
    ("Match Pricing", "⚽"),
    ("Historical Research", "📊"),
    ("Database Health", "🗄️"),
]:
    active = st.session_state.active_page == page

    if st.button(
        f"{icon}  {page}",
        key=f"nav_{page}",
        width="stretch",
        type="primary" if active else "secondary",
    ):
        st.session_state.active_page = page
        st.rerun()

st.divider()

# --------------------------------------------------
# MATCH PRICING - UNCHANGED PLACEHOLDER
# --------------------------------------------------

if st.session_state.active_page == "Match Pricing":
    st.header("Match Pricing")

    st.caption(
        "Pre-match and in-play football "
        "pricing terminal"
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

# --------------------------------------------------
# HISTORICAL RESEARCH
# --------------------------------------------------

elif st.session_state.active_page == "Historical Research":
    st.header("Historical Research")

    st.caption(
        "Two-team domestic league comparison. "
        "Read-only Supabase research."
    )

    st.subheader("Home team")

    home_search = st.text_input(
        "Search home team",
        placeholder="e.g. Newcastle",
        key="home_research_search",
        max_chars=60,
    ).strip()

    home_team = None

    if len(home_search) >= 3:
        if "%" in home_search or "_" in home_search:
            st.warning(
                "Please avoid % and _ "
                "in team searches."
            )
        else:
            try:
                home_options = find_team_names(
                    home_search
                )

                if home_options:
                    home_team = st.selectbox(
                        "Choose home team",
                        home_options,
                    )
                else:
                    st.warning(
                        "No matching home team found."
                    )

            except Exception as exc:
                st.error(
                    "Home-team search failed: "
                    f"{type(exc).__name__}"
                )

    st.subheader("Away team")

    away_search = st.text_input(
        "Search away team",
        placeholder="e.g. Everton",
        key="away_research_search",
        max_chars=60,
    ).strip()

    away_team = None

    if len(away_search) >= 3:
        if "%" in away_search or "_" in away_search:
            st.warning(
                "Please avoid % and _ "
                "in team searches."
            )
        else:
            try:
                away_options = find_team_names(
                    away_search
                )

                if away_options:
                    away_team = st.selectbox(
                        "Choose away team",
                        away_options,
                    )
                else:
                    st.warning(
                        "No matching away team found."
                    )

            except Exception as exc:
                st.error(
                    "Away-team search failed: "
                    f"{type(exc).__name__}"
                )

    st.subheader("Research settings")

    overall_count = st.select_slider(
        "Overall league matches per team",
        options=[5, 10, 15, 20, 30, 50],
        value=20,
    )

    venue_count = st.select_slider(
        "Home/away league matches per team",
        options=[5, 10, 15, 20, 30],
        value=10,
    )

    as_of = st.date_input(
        "Include matches up to",
        value=date.today(),
        max_value=date.today(),
    )

    ready = (
        home_team is not None
        and away_team is not None
        and home_team != away_team
    )

    if st.button(
        "📊 Compare both teams",
        type="primary",
        width="stretch",
        disabled=not ready,
    ):
        st.session_state["comparison_selection"] = (
            home_team,
            away_team,
            overall_count,
            venue_count,
            as_of.isoformat(),
        )

    current = (
        home_team,
        away_team,
        overall_count,
        venue_count,
        as_of.isoformat(),
    )

    selected = st.session_state.get(
        "comparison_selection"
    )

    if ready and selected == current:
        try:
            show_comparison(
                home_team,
                away_team,
                overall_count,
                venue_count,
                as_of.isoformat(),
            )

        except Exception as exc:
            st.error(
                "Comparison failed "
                f"({type(exc).__name__}). "
                "No data has been changed."
            )

    st.caption(
        "Corners, cards and event timelines "
        "will be added after the historical "
        "events database is joined and "
        "verification rules are implemented."
    )

# --------------------------------------------------
# DATABASE HEALTH - UNCHANGED
# --------------------------------------------------

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
                st.error(f"{label}: {kind}")
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
