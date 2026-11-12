
import streamlit as st
import pandas as pd
from datetime import date
from supabase import create_client

from starlizard_experimental_pricing import estimate as estimate_xg, probabilities as poisson_prices
from starlizard_opponent_adjustment import adjust_venue_rows
from starlizard_live_fixtures import render_live_fixtures
from starlizard_stored_odds import render_historical_odds
from starlizard_halftime_markets_v57 import render_halftime_markets

# ==================================================
# PRO STARLIZARD — MAIN DASHBOARD
#
# V5.7 memory-efficient halftime markets integrated.
# Historical calculations run only when requested.
#
# All database operations are read-only.
# ==================================================

st.set_page_config(
    page_title="PRO STARLIZARD",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
.stApp {
    background:#0b1220;
    color:#e8eef8;
}
.block-container {
    padding-top:4.5rem!important;
    padding-bottom:2rem;
    max-width:1100px;
}
h1,h2,h3 {
    color:#f8fafc!important;
}
label,
[data-testid="stWidgetLabel"],
[data-testid="stWidgetLabel"] p {
    color:#e8eef8!important;
    font-weight:600!important;
}
div[data-testid="stMetric"] {
    background:#172338;
    border:1px solid #293a53;
    border-radius:12px;
    padding:12px;
}
div[data-testid="stMetricValue"],
div[data-testid="stMetricValue"] *,
div[data-testid="stMetricLabel"],
div[data-testid="stMetricLabel"] * {
    color:#f8fafc!important;
    opacity:1!important;
}
div.stButton>button {
    width:100%;
    min-height:3.2rem;
    border-radius:12px;
    font-size:1rem;
    font-weight:700;
    border:1px solid #41536c;
}
div.stButton>button[kind="primary"] {
    background:#b91c38;
    border-color:#ef4766;
    color:white;
}
div.stButton>button[kind="secondary"] {
    background:#172338;
    color:#f8fafc;
}
div.stButton>button p {
    color:inherit!important;
}
/* Make model navigation as touch-friendly as the main dashboard buttons. */
div[data-testid="stPageLink"] a {
    display:flex!important;
    align-items:center!important;
    justify-content:center!important;
    width:100%!important;
    min-height:4.4rem!important;
    padding:1rem!important;
    background:#172338!important;
    border:1px solid #41536c!important;
    border-radius:15px!important;
    color:#f8fafc!important;
    text-decoration:none!important;
    font-size:1.05rem!important;
    font-weight:650!important;
    text-align:center!important;
}
div[data-testid="stPageLink"] a:hover,
div[data-testid="stPageLink"] a:focus-visible {
    background:#223653!important;
    border-color:#8fa6c6!important;
}
div[data-testid="stPageLink"] a p,
div[data-testid="stPageLink"] a span {
    color:#f8fafc!important;
}
/* Sidebar navigation is compact; main-page model buttons stay large. */
section[data-testid="stSidebar"] div[data-testid="stPageLink"] a {
    min-height:2.7rem!important;
    padding:0.5rem 0.7rem!important;
    border-radius:10px!important;
    font-size:0.92rem!important;
    font-weight:600!important;
    justify-content:flex-start!important;
    text-align:left!important;
}
section[data-testid="stSidebar"] div[data-testid="stPageLink"] {
    margin-bottom:0!important;
}
[data-testid="stImage"] img {
    object-fit:contain!important;
    height:auto!important;
}
@media(max-width:640px) {
    .block-container {
        padding-top:4rem!important;
        padding-left:1rem;
        padding-right:1rem;
    }
    h1 {
        font-size:1.8rem!important;
    }
    h2 {
        font-size:1.4rem!important;
    }
}
</style>
""", unsafe_allow_html=True)

st.image(
    "pro_starlizard_header_correct-1.png",
    width="stretch",
)

# Curated sidebar replaces Streamlit's automatic list of development pages.
with st.sidebar:
    st.markdown("### 🦎 PRO STARLIZARD")
    st.caption("Quick navigation")
    st.page_link("pro_starlizard.py", label="🏠 Main dashboard", use_container_width=True)
    st.page_link("pages/Live_Fixture_Bridge.py", label="⚽ Fixtures & pricing", use_container_width=True)
    st.page_link("pages/Halftime_Pricing_Lab.py", label="🧠 Half-time pricing", use_container_width=True)
    st.page_link("pages/Halftime_Intelligence.py", label="🔎 Half-time research", use_container_width=True)
    st.page_link("pages/Model_Intelligence.py", label="📈 Model intelligence", use_container_width=True)
    st.page_link("pages/Automatic_Pattern_Scanner.py", label="🦎 Pattern scanner", use_container_width=True)
    st.page_link("pages/Archive_Historical_Research.py", label="🗃️ Historical archive", use_container_width=True)
    st.caption("All research tools remain available; developer pages are hidden from navigation, not deleted.")

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

LEAGUE_IDS = list(LEAGUES)

FIELDS = (
    "match_id,competition_id,match_date,"
    "home_team,away_team,home_goals,away_goals,"
    "home_ht_goals,away_ht_goals,"
    "home_xg,away_xg,home_ht_xg,away_ht_xg"
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
    ("2H goals scored", "2H GF"),
    ("2H goals conceded", "2H GA"),
]

SAMPLE_OPTIONS = [5, 10, 15, 20, 25]


# ==================================================
# SUPABASE CONNECTION
# ==================================================

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

            results[label] = (
                query.limit(1).execute().count
            )

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
            if row.get(field):
                found.add(row[field])

    return sorted(found, key=str.casefold)


def numeric(value):
    try:
        if value is None or value == "":
            return None

        result = float(value)

        if pd.notna(result):
            return result

        return None

    except (TypeError, ValueError):
        return None


def has_score(row):
    return (
        numeric(row.get("home_goals")) is not None
        and numeric(row.get("away_goals")) is not None
    )


# ==================================================
# HISTORICAL MATCH RETRIEVAL
# ==================================================

@st.cache_data(ttl=300, show_spinner=False)
def get_matches(team, count, as_of, venue="All"):
    db = get_supabase()

    if venue == "Home":
        fields = ["home_team"]
    elif venue == "Away":
        fields = ["away_team"]
    else:
        fields = ["home_team", "away_team"]

    records = []

    for field in fields:
        response = (
            db.table("historical_xg")
            .select(FIELDS)
            .eq(field, team)
            .in_("competition_id", LEAGUE_IDS)
            .lte("match_date", as_of)
            .order("match_date", desc=True)
            .limit(max(150, count * 4))
            .execute()
        )

        records.extend(response.data or [])

    unique = {
        str(row["match_id"]): row
        for row in records
        if row.get("match_id") is not None
    }

    ordered = sorted(
        unique.values(),
        key=lambda r: (
            r.get("match_date") or "",
            str(r.get("match_id") or ""),
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


@st.cache_data(ttl=3600, show_spinner=False)
def get_league_strength_history(competition_id, cutoff):
    """Read up to 2,000 league fixtures, strictly earlier than cutoff."""
    db = get_supabase()
    rows = []
    for offset in (0, 1000):
        response = (
            db.table("historical_xg")
            .select("match_id,match_date,home_team,away_team,home_xg,away_xg")
            .eq("competition_id", competition_id)
            .lt("match_date", str(cutoff))
            .order("match_date", desc=True)
            .range(offset, offset + 999)
            .execute()
        )
        batch = response.data or []
        rows.extend(batch)
        if len(batch) < 1000:
            break
    return rows


def adjusted_venue_frames(home_df, away_df, as_of):
    """Adjust each observation against opponent strength before its date."""
    league_by_name = {name: code for code, name in LEAGUES.items()}
    league_names = set(home_df["League"]).union(set(away_df["League"]))
    history = []
    capped = False
    for name in league_names:
        code = league_by_name.get(name)
        if code is None:
            continue
        rows = get_league_strength_history(code, as_of)
        capped = capped or len(rows) >= 2000
        history.extend(rows)
    home_adj, hu, he = adjust_venue_rows(home_df, history)
    away_adj, au, ae = adjust_venue_rows(away_df, history)
    return home_adj, away_adj, hu + au, he + ae, capped


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
        "2H GF",
        "2H GA",
        "xGF",
        "xGA",
        "HT xGF",
        "HT xGA",
        "Result",
    ]

    rows = []

    for match in matches:
        home = match.get("home_team") == team

        def pair(h, a):
            return (
                numeric(match.get(h if home else a)),
                numeric(match.get(a if home else h)),
            )

        gf, ga = pair(
            "home_goals",
            "away_goals",
        )

        hgf, hga = pair(
            "home_ht_goals",
            "away_ht_goals",
        )

        xgf, xga = pair(
            "home_xg",
            "away_xg",
        )

        hxgf, hxga = pair(
            "home_ht_xg",
            "away_ht_xg",
        )

        shgf = (
            gf - hgf
            if gf is not None and hgf is not None
            else None
        )

        shga = (
            ga - hga
            if ga is not None and hga is not None
            else None
        )

        result = (
            "W"
            if gf > ga
            else "L"
            if gf < ga
            else "D"
        )

        rows.append({
            "Date": match.get("match_date"),
            "League": LEAGUES.get(
                match.get("competition_id"),
                "Unknown",
            ),
            "Venue": "Home" if home else "Away",
            "Opponent": (
                match.get("away_team")
                if home
                else match.get("home_team")
            ),
            "GF": gf,
            "GA": ga,
            "HT GF": hgf,
            "HT GA": hga,
            "2H GF": shgf,
            "2H GA": shga,
            "xGF": xgf,
            "xGA": xga,
            "HT xGF": hxgf,
            "HT xGA": hxga,
            "Result": result,
        })

    return pd.DataFrame(
        rows,
        columns=columns,
    )


def average(df, column):
    if df.empty:
        return None

    values = pd.to_numeric(
        df[column],
        errors="coerce",
    ).dropna()

    return (
        float(values.mean())
        if len(values)
        else None
    )


def fmt(value):
    return (
        f"{value:.2f}"
        if value is not None
        else "—"
    )


def record_text(df):
    if df.empty:
        return "No matches"

    wins = (df["Result"] == "W").sum()
    draws = (df["Result"] == "D").sum()
    losses = (df["Result"] == "L").sum()

    return f"{wins}W / {draws}D / {losses}L"


def form_badges(df):
    if df.empty:
        st.caption("No matches")
        return

    colors = {
        "W": "#15803d",
        "D": "#2563eb",
        "L": "#b91c1c",
    }

    cells = "".join(
        (
            f'<span style="display:inline-block;'
            f'background:{colors[r]};'
            f'color:white;'
            f'border-radius:6px;'
            f'padding:6px 10px;'
            f'margin:3px 3px 3px 0;'
            f'font-weight:700">{r}</span>'
        )
        for r in df["Result"].tolist()
    )

    st.markdown(
        cells,
        unsafe_allow_html=True,
    )

    st.caption(
        "Most recent first · "
        "Green win · Blue draw · Red loss"
    )


def styled_matches(df):
    if df.empty:
        st.info(
            "No completed league matches found."
        )
        return

    def colour_result(value):
        return {
            "W": (
                "background-color:#15803d;"
                "color:white;font-weight:bold"
            ),
            "D": (
                "background-color:#2563eb;"
                "color:white;font-weight:bold"
            ),
            "L": (
                "background-color:#b91c1c;"
                "color:white;font-weight:bold"
            ),
        }.get(value, "")

    display = df.copy()

    for column in [
        "GF",
        "GA",
        "HT GF",
        "HT GA",
        "2H GF",
        "2H GA",
    ]:
        display[column] = display[column].map(
            lambda value: (
                int(value)
                if pd.notna(value)
                else None
            )
        )

    st.dataframe(
        display.style.map(
            colour_result,
            subset=["Result"],
        ),
        hide_index=True,
        width="stretch",
    )


def comparison_table(
    home_name,
    away_name,
    home_df,
    away_df,
):
    rows = []

    for label, column in METRICS:

        def cell(df):
            if df.empty:
                return "—"

            values = pd.to_numeric(
                df[column],
                errors="coerce",
            ).dropna()

            if len(values):
                return (
                    f"{values.mean():.2f} "
                    f"(n={len(values)})"
                )

            return "—"

        rows.append({
            "Statistic": label,
            "Home team": cell(home_df),
            "Away team": cell(away_df),
        })

    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        width="stretch",
        column_config={
            "Statistic": (
                st.column_config.TextColumn(
                    "Statistic"
                )
            ),
            "Home team": (
                st.column_config.TextColumn(
                    home_name
                )
            ),
            "Away team": (
                st.column_config.TextColumn(
                    away_name
                )
            ),
        },
    )


# ==================================================
# HISTORICAL BETTING ANGLE SCREENING
# ==================================================

def market_observation(df, market):
    if df.empty:
        return 0, 0

    hits = 0
    eligible = 0

    for _, row in df.iterrows():
        gf = numeric(row["GF"])
        ga = numeric(row["GA"])
        hgf = numeric(row["HT GF"])
        hga = numeric(row["HT GA"])

        if gf is None or ga is None:
            continue

        total = gf + ga

        if market == "Over 1.5 goals":
            result = total >= 2

        elif market == "Over 2.5 goals":
            result = total >= 3

        elif market == "Over 3.5 goals":
            result = total >= 4

        elif market == "BTTS Yes":
            result = gf >= 1 and ga >= 1

        elif market == "BTTS No":
            result = gf == 0 or ga == 0

        elif market == "Over 0.5 first-half goals":
            if hgf is None or hga is None:
                continue
            result = hgf + hga >= 1

        elif market == "Over 1.5 first-half goals":
            if hgf is None or hga is None:
                continue
            result = hgf + hga >= 2

        elif market == "Over 0.5 second-half goals":
            if hgf is None or hga is None:
                continue
            result = total - hgf - hga >= 1

        elif market == "Over 1.5 second-half goals":
            if hgf is None or hga is None:
                continue
            result = total - hgf - hga >= 2

        elif market == "Home team to score":
            result = (
                gf >= 1
                if row["Venue"] == "Home"
                else ga >= 1
            )

        elif market == "Away team to score":
            result = (
                ga >= 1
                if row["Venue"] == "Home"
                else gf >= 1
            )

        elif market == "Home win":
            result = (
                gf > ga
                if row["Venue"] == "Home"
                else ga > gf
            )

        elif market == "Draw":
            result = gf == ga

        elif market == "Away win":
            result = (
                ga > gf
                if row["Venue"] == "Home"
                else gf > ga
            )

        elif market == "Home or draw":
            result = (
                gf >= ga
                if row["Venue"] == "Home"
                else ga >= gf
            )

        elif market == "Away or draw":
            result = (
                ga >= gf
                if row["Venue"] == "Home"
                else gf >= ga
            )

        else:
            continue

        eligible += 1
        hits += int(result)

    return hits, eligible


def betting_angles(
    home_df,
    away_df,
    home_name,
    away_name,
):
    st.header("Potential betting angles")

    st.caption(
        "Historical screening only — "
        "no bookmaker odds, no calibrated "
        "probabilities, and no claim "
        "of positive expected value."
    )

    if len(home_df) < 5 or len(away_df) < 5:
        st.info(
            "At least five completed home "
            "and five completed away league "
            "matches are required."
        )
        return

    markets = [
        "Over 1.5 goals",
        "Over 2.5 goals",
        "Over 3.5 goals",
        "BTTS Yes",
        "BTTS No",
        "Over 0.5 first-half goals",
        "Over 1.5 first-half goals",
        "Over 0.5 second-half goals",
        "Over 1.5 second-half goals",
        "Home team to score",
        "Away team to score",
        "Home win",
        "Draw",
        "Away win",
        "Home or draw",
        "Away or draw",
    ]

    suggestions = []

    for market in markets:
        h, hn = market_observation(
            home_df,
            market,
        )

        a, an = market_observation(
            away_df,
            market,
        )

        if hn < 5 or an < 5:
            continue

        hp = h / hn
        ap = a / an

        if min(hp, ap) < 0.60:
            continue

        suggestions.append((
            min(hp, ap),
            (h + a) / (hn + an),
            market,
            h,
            hn,
            a,
            an,
        ))

    suggestions.sort(reverse=True)

    if not suggestions:
        st.info(
            "No market met the screening rule: "
            "at least 60% in each venue sample. "
            "This does not mean there are "
            "no possible bets."
        )
        return

    st.caption(
        "Each team's venue sample must show "
        "the outcome in at least 60% of "
        "eligible matches. Ranked by the "
        "weaker observed rate."
    )

    for (
        _,
        pooled,
        market,
        h,
        hn,
        a,
        an,
    ) in suggestions[:3]:

        with st.container(border=True):
            st.markdown(f"**{market}**")

            c1, c2 = st.columns(2)

            with c1:
                st.metric(
                    f"{home_name} home",
                    f"{h}/{hn}",
                    f"{h / hn:.0%}",
                    delta_color="off",
                )

            with c2:
                st.metric(
                    f"{away_name} away",
                    f"{a}/{an}",
                    f"{a / an:.0%}",
                    delta_color="off",
                )

            # Descriptive inverse frequency only: not a calibrated fair quote.
            inverse_odds = f"{1 / pooled:.2f}" if pooled > 0 else "—"
            st.markdown(
                f"**Historical break-even odds: {inverse_odds}**"
                f" · {h + a}/{hn + an} ({pooled:.0%})"
            )
            st.caption(
                "Inverse of the pooled historical hit rate, NOT a "
                "fixture-specific fair price. Small venue samples, "
                "opponent strength and selection effects can distort it."
            )

    st.info(
        "These are research leads, not "
        "betting recommendations. Markets "
        "are correlated, opponent strength "
        "is not adjusted, and market odds "
        "are essential for assessing value."
    )


# ==================================================
# TWO-TEAM COMPARISON
# ==================================================

def fixture_prematch_rates(home_team, away_team, match_day):
    """Historical-only rates for the live halftime view; never include match day."""
    from datetime import timedelta
    cutoff = (match_day - timedelta(days=1)).isoformat()
    home_rows, _ = get_matches(home_team, 25, cutoff, "Home")
    away_rows, _ = get_matches(away_team, 25, cutoff, "Away")
    home_df = build_dataframe(home_team, home_rows)
    away_df = build_dataframe(away_team, away_rows)
    adjusted_home, adjusted_away, used, eligible, capped = (
        adjusted_venue_frames(home_df, away_df, cutoff)
    )
    if used >= 10:
        estimated = estimate_xg(adjusted_home, adjusted_away)
        if estimated is not None:
            return estimated[0], estimated[1], f"opponent-adjusted ({used}/{eligible} observations)"
    estimated = estimate_xg(home_df, away_df)
    if estimated is None:
        return None
    return estimated[0], estimated[1], "basic xG fallback (insufficient opponent history)"


def show_comparison(
    home_team,
    away_team,
    home_count,
    away_count,
    overall_count,
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
            home_count,
            as_of,
            "Home",
        )

        away_venue, away_venue_missing = get_matches(
            away_team,
            away_count,
            as_of,
            "Away",
        )

    hadf = build_dataframe(
        home_team,
        home_all,
    )

    aadf = build_dataframe(
        away_team,
        away_all,
    )

    hvdf = build_dataframe(
        home_team,
        home_venue,
    )

    avdf = build_dataframe(
        away_team,
        away_venue,
    )

    st.success(
        "Domestic league comparison loaded."
    )

    st.caption(
        "League-only records; cup and "
        "European fixtures excluded. "
        "Latest matches first."
    )

    st.header("Home versus away form")

    c1, c2 = st.columns(2)

    with c1:
        st.markdown(
            f"**{home_team} — HOME**"
        )
        st.metric("Matches", len(hvdf))
        st.write(record_text(hvdf))
        form_badges(hvdf)

    with c2:
        st.markdown(
            f"**{away_team} — AWAY**"
        )
        st.metric("Matches", len(avdf))
        st.write(record_text(avdf))
        form_badges(avdf)

    comparison_table(
        home_team,
        away_team,
        hvdf,
        avdf,
    )

    st.subheader("🧮 Experimental xG model prices")
    st.caption(
        "Pre-match independent-Poisson model, with historical opponent "
        "strength adjustments where sufficient data exist. NOT calibrated or backtested; "
        "not a verified betting edge."
    )
    try:
        with st.spinner("Adjusting xG for historical opponent strength..."):
            adj_home, adj_away, adjusted_n, eligible_n, history_capped = (
                adjusted_venue_frames(hvdf, avdf, as_of)
            )
        adjusted_estimate = estimate_xg(adj_home, adj_away)
    except Exception as exc:
        st.warning(f"Opponent adjustment unavailable: {exc}")
        adjusted_estimate = None
        adjusted_n, eligible_n, history_capped = 0, 0, False
    basic_estimate = estimate_xg(hvdf, avdf)
    estimated = (
        adjusted_estimate if adjusted_estimate is not None and adjusted_n >= 10
        else basic_estimate
    )
    if estimated is not None and adjusted_estimate is not None and adjusted_n >= 10:
        st.caption(
            f"Opposition-adjusted xG: {adjusted_n}/{eligible_n} "
            "historical venue observations adjusted using strictly earlier "
            "league matches. Opponent ratings are shrunk and capped."
        )
        if history_capped:
            st.warning(
                "League-strength history reached its 2,000-match per-league "
                "limit; older opponent histories may be incomplete."
            )
        if basic_estimate is not None:
            st.caption(
                f"Basic model rates for comparison: "
                f"{basic_estimate[0]:.2f} – {basic_estimate[1]:.2f}"
            )
    else:
        st.warning(
            "Not enough supported historical opponent adjustments; "
            "showing the basic xG model instead."
        )
    if estimated is None:
        st.info("Need at least five valid venue xG observations for each component.")
    else:
        home_rate, away_rate, sample_counts = estimated
        st.caption(
            f"Model goal rates: {home_team} {home_rate:.2f} · "
            f"{away_team} {away_rate:.2f} "
            f"· xG component samples: {sample_counts}"
        )
        prices = poisson_prices(home_rate, away_rate)
        display_markets = [
            "Home win", "Draw", "Away win", "Home or draw",
            "Away or draw", "Home team to score", "Away team to score",
            "BTTS Yes", "BTTS No", "Over 1.5 goals",
            "Over 2.5 goals", "Over 3.5 goals",
        ]
        st.dataframe(pd.DataFrame([
            {
                "Market": market,
                "Model probability": f"{prices[market]:.1%}",
                "Indicative odds": f"{1/prices[market]:.2f}"
                if prices[market] > 0 else "—",
            }
            for market in display_markets
        ]), hide_index=True, use_container_width=True)
        st.caption(
            "Indicative odds = 1 / model probability. "
            "No bookmaker margin; no half-specific markets yet. "
            "Validation against unseen fixtures is required."
        )

    betting_angles(
        hvdf,
        avdf,
        home_team,
        away_team,
    )

    st.header("Attack versus defence")

    st.caption(
        "Historical venue averages, "
        "not opposition-adjusted forecasts."
    )

    st.dataframe(
        pd.DataFrame([
            {
                "Comparison": (
                    f"{home_team} attack"
                ),
                "Attacking xG": fmt(
                    average(hvdf, "xGF")
                ),
                "Opponent xG conceded": fmt(
                    average(avdf, "xGA")
                ),
            },
            {
                "Comparison": (
                    f"{away_team} attack"
                ),
                "Attacking xG": fmt(
                    average(avdf, "xGF")
                ),
                "Opponent xG conceded": fmt(
                    average(hvdf, "xGA")
                ),
            },
        ]),
        hide_index=True,
        width="stretch",
    )

    with st.expander(
        f"Overall form — last {overall_count} "
        "league matches per team"
    ):
        c1, c2 = st.columns(2)

        with c1:
            st.markdown(
                f"**{home_team}**"
            )
            st.write(record_text(hadf))
            form_badges(hadf)

        with c2:
            st.markdown(
                f"**{away_team}**"
            )
            st.write(record_text(aadf))
            form_badges(aadf)

        comparison_table(
            home_team,
            away_team,
            hadf,
            aadf,
        )

    st.header("Match-by-match records")

    with st.expander(
        f"{home_team} — last {home_count} "
        "HOME league matches"
    ):
        styled_matches(hvdf)

    with st.expander(
        f"{away_team} — last {away_count} "
        "AWAY league matches"
    ):
        styled_matches(avdf)

    with st.expander(
        f"{home_team} — overall league matches"
    ):
        styled_matches(hadf)

    with st.expander(
        f"{away_team} — overall league matches"
    ):
        styled_matches(aadf)

    render_historical_odds(home_all + away_all)

    st.header("Data quality")

    samples = [
        (
            f"{home_team} overall",
            len(hadf),
            overall_count,
            len(home_all_missing),
        ),
        (
            f"{away_team} overall",
            len(aadf),
            overall_count,
            len(away_all_missing),
        ),
        (
            f"{home_team} home",
            len(hvdf),
            home_count,
            len(home_venue_missing),
        ),
        (
            f"{away_team} away",
            len(avdf),
            away_count,
            len(away_venue_missing),
        ),
    ]

    issues = False

    for label, found, requested, missing in samples:
        if found < requested:
            issues = True
            st.warning(
                f"{label}: {found}/{requested} "
                "completed matches available."
            )

        if missing:
            issues = True
            st.warning(
                f"{label}: {missing} "
                "incomplete-score records encountered."
            )

    if not issues:
        st.success(
            "All four requested samples "
            "have completed scores."
        )

    st.caption(
        "Averages exclude missing metric "
        "values. Historical rates are not "
        "opponent-adjusted and may not "
        "reflect current squads or strength."
    )


# ==================================================
# NAVIGATION
# ==================================================

if "active_page" not in st.session_state:
    st.session_state.active_page = "Home"

if st.session_state.active_page == "Home":
    st.subheader("⚽ Match centre")
    st.caption("Choose a fixture to view its actual match state and available halftime research.")
    if st.button("🔴 Live Fixtures — Select a Match", type="primary", key="nav_live_main", width="stretch"):
        st.session_state.active_page = "Live Fixtures"
        st.rerun()

    with st.expander("Other dashboard tools", expanded=False):
        for page, label in [
            ("Historical Research", "📊 Team historical comparison"),
            ("Database Health", "🗄️ Database health"),
            ("Match Pricing", "✍️ Manual halftime research"),
        ]:
            if st.button(label, key=f"nav_extra_{page}", width="stretch"):
                st.session_state.active_page = page
                st.rerun()

    st.divider()
    st.subheader("🧠 Models & research")
    st.caption("Choose a specialist model or research workspace. These tools remain available without cluttering the main screen.")
    model_pages = [
        ("⚽ Fixture pricing", "pages/Live_Fixture_Bridge.py", "Fixture-based goals and Asian-market research"),
        ("🧠 Half-time pricing lab", "pages/Halftime_Pricing_Lab.py", "Half-time pricing scenarios and research"),
        ("🔎 Half-time intelligence", "pages/Halftime_Intelligence.py", "Second-half and next-goal historical patterns"),
        ("📈 Model intelligence", "pages/Model_Intelligence.py", "Archive coverage, model readiness and saved findings"),
        ("🦎 Automatic pattern scanner", "pages/Automatic_Pattern_Scanner.py", "Explore statistically screened historical patterns"),
        ("🗃️ Historical archive", "pages/Archive_Historical_Research.py", "Inspect linked historical match data"),
    ]
    for label, destination, description in model_pages:
        st.page_link(destination, label=label, use_container_width=True)
        st.caption(description)
        st.write("")

else:
    if st.button("🏠 Back to dashboard", key="nav_home", width="stretch"):
        st.session_state.active_page = "Home"
        st.rerun()
    st.divider()


# ==================================================
# PAGE 1 — MATCH PRICING
# ==================================================

if st.session_state.active_page == "Match Pricing":

    st.header("Match Pricing")

    st.caption(
        "PRO STARLIZARD | V5.7 historical "
        "halftime corners and cards"
    )

    st.info(
        "Choose Live Fixtures above to select a match. "
        "The match screen retrieves available score, xG, corners "
        "and cards from TheStatsAPI and offers automatic halftime research."
    )

    if st.button("🔴 Choose a live fixture", type="primary", key="pricing_go_live", width="stretch"):
        st.session_state.active_page = "Live Fixtures"
        st.rerun()

    with st.expander("✍️ Manual halftime entry (optional)", expanded=False):
        st.caption("Use this only when you want to research a hypothetical match or enter verified figures yourself.")
        render_halftime_markets(get_supabase())


# ==================================================
# PAGE 2 — HISTORICAL RESEARCH
# ==================================================

elif (
    st.session_state.active_page
    == "Historical Research"
):

    st.header("Historical Research")

    st.caption(
        "Two-team, venue-specific league "
        "comparison. Read-only Supabase research."
    )

    st.subheader("Choose your teams")

    home_search = st.text_input(
        "Search HOME team",
        placeholder="e.g. Manchester",
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
                opts = find_team_names(
                    home_search
                )

                if opts:
                    home_team = st.selectbox(
                        "Home team",
                        opts,
                        key="research_home_team",
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

    away_search = st.text_input(
        "Search AWAY team",
        placeholder="e.g. Aston",
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
                opts = find_team_names(
                    away_search
                )

                if opts:
                    away_team = st.selectbox(
                        "Away team",
                        opts,
                        key="research_away_team",
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

    st.subheader(
        "Select recent league matches"
    )

    c1, c2 = st.columns(2)

    with c1:
        home_count = st.selectbox(
            "HOME matches",
            SAMPLE_OPTIONS,
            index=1,
            key="research_home_count",
        )

    with c2:
        away_count = st.selectbox(
            "AWAY matches",
            SAMPLE_OPTIONS,
            index=1,
            key="research_away_count",
        )

    with st.expander(
        "Optional: overall form settings"
    ):
        overall_count = st.selectbox(
            "Overall league matches per team",
            [5, 10, 15, 20, 25, 30, 50],
            index=3,
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
        "📊 Analyse this fixture",
        type="primary",
        width="stretch",
        disabled=not ready,
    ):
        st.session_state[
            "comparison_selection"
        ] = (
            home_team,
            away_team,
            home_count,
            away_count,
            overall_count,
            as_of.isoformat(),
        )

    current = (
        home_team,
        away_team,
        home_count,
        away_count,
        overall_count,
        as_of.isoformat(),
    )

    if (
        ready
        and st.session_state.get(
            "comparison_selection"
        ) == current
    ):
        try:
            show_comparison(*current)
        except Exception as exc:
            st.error(
                "Comparison failed "
                f"({type(exc).__name__}). "
                "No data has been changed."
            )

    st.caption(
        "Historical team research remains "
        "separate from V5.7 halftime pricing."
    )


# ==================================================
# PAGE 3 — LIVE FIXTURES
# ==================================================

elif (
    st.session_state.active_page
    == "Live Fixtures"
):

    render_live_fixtures(
        LEAGUES,
        find_team_names,
        show_comparison,
        fixture_prematch_rates,
    )


# ==================================================
# PAGE 4 — DATABASE HEALTH
# ==================================================

elif (
    st.session_state.active_page
    == "Database Health"
):

    st.header("Database Health")

    st.caption(
        "Live historical collection "
        "statistics from Supabase"
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
                "All seven database "
                "checks succeeded."
            )
        else:
            st.warning(
                f"{passed} of 7 database "
                "checks succeeded."
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

        st.subheader(
            "Database Diagnostics"
        )

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
            "Read-only queries. Figures cached "
            "for two minutes. Received timelines "
            "are not independently goal-verified "
            "by this dashboard."
        )

    except Exception as exc:
        st.error(
            "Database connection failed "
            f"({type(exc).__name__})."
        )


# ==================================================
# FOOTER
# ==================================================

st.divider()

st.caption(
    "PRO STARLIZARD | V5.7 integrated | "
    "Research and model estimates only. "
    "No automated betting."
)

st.caption(
    "🦎 Scrumpy & Lady Sally — "
    "Data Acquisition Team"
)
