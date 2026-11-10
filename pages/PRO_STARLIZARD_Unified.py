
"""
PRO STARLIZARD — Unified Dashboard V2

Mobile-friendly historical pricing interface.

Features:
- Read-only Supabase connection
- Historical halftime scenario matching
- Goals, corners and yellow-card pricing
- Compact mobile-friendly pricing tables
- Historical fair decimal odds
- Sample-size warnings

Existing pricing engine remains unchanged.
"""

import os
from datetime import date

import streamlit as st
from supabase import create_client

from starlizard_unified_pricing import (
    load_table,
    build_matches,
    comparable_matches,
    price_market,
    home_scores_second_half,
    away_scores_second_half,
    home_wins_second_half,
    over_goals,
    market_over,
)


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="PRO STARLIZARD Unified",
    page_icon="🦎",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ============================================================
# MOBILE STYLING
# ============================================================

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 2rem;
        max-width: 1100px;
    }

    h1 {
        font-size: 2rem !important;
        margin-bottom: 0.2rem;
    }

    h2 {
        font-size: 1.35rem !important;
        margin-top: 0.8rem;
    }

    div[data-testid="stMetricValue"] {
        font-size: 1.6rem;
    }

    div[data-testid="stDataFrame"] {
        font-size: 0.85rem;
    }

    @media (max-width: 600px) {
        .block-container {
            padding-left: 0.7rem;
            padding-right: 0.7rem;
        }

        h1 {
            font-size: 1.7rem !important;
        }

        h2 {
            font-size: 1.2rem !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# HEADER
# ============================================================

st.title("🦎 PRO STARLIZARD")

st.caption(
    "Unified historical pricing | Goals • Corners • Cards"
)

st.info(
    "Historical probabilities, not yet calibrated "
    "predictive prices."
)


# ============================================================
# DATABASE CONNECTION
# ============================================================

@st.cache_resource
def database():
    url = (
        st.secrets.get("SUPABASE_URL")
        or os.environ.get("SUPABASE_URL")
    )

    key = (
        st.secrets.get("SUPABASE_SECRET_KEY")
        or os.environ.get("SUPABASE_SECRET_KEY")
    )

    if not url or not key:
        raise RuntimeError(
            "Missing SUPABASE_URL or SUPABASE_SECRET_KEY"
        )

    return create_client(url, key)


# ============================================================
# LOAD HISTORICAL DATA
# ============================================================

@st.cache_data(
    ttl=3600,
    show_spinner="Loading PRO STARLIZARD historical data..."
)
def historical_matches():

    db = database()

    xg_rows = load_table(
        db,
        "historical_xg",
        "match_id,match_date,competition_id,"
        "home_ht_goals,away_ht_goals,"
        "home_goals,away_goals,"
        "home_ht_xg,away_ht_xg",
    )

    event_rows = load_table(
        db,
        "historical_match_events",
        "match_id,stats_data",
    )

    matches, rejected = build_matches(
        xg_rows,
        event_rows,
    )

    return matches, rejected


# ============================================================
# COMPACT PRICING TABLE
# ============================================================

def show_markets(matches, markets):

    rows = []

    for label, predicate in markets:

        result = price_market(
            matches,
            predicate,
        )

        if result is None:
            rows.append({
                "Market": label,
                "Prob.": "—",
                "Fair": "—",
                "N": "0",
            })
            continue

        warning = (
            " ⚠️"
            if not result["sufficient_sample"]
            else ""
        )

        rows.append({
            "Market": label + warning,
            "Prob.": f"{result['probability']:.1%}",
            "Fair": f"{result['fair_odds']:.2f}",
            "N": str(result["sample"]),
        })

    st.dataframe(
        rows,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Market": st.column_config.TextColumn(
                "Market",
                width="large",
            ),
            "Prob.": st.column_config.TextColumn(
                "Prob.",
                width="small",
            ),
            "Fair": st.column_config.TextColumn(
                "Fair",
                width="small",
            ),
            "N": st.column_config.TextColumn(
                "N",
                width="small",
            ),
        },
    )


# ============================================================
# INITIALISE DATA
# ============================================================

try:
    matches, rejected = historical_matches()

except Exception as exc:
    st.error(
        f"Historical data could not be loaded: {exc}"
    )
    st.stop()


st.success(
    f"{len(matches):,} historical matches loaded"
)


# ============================================================
# HALFTIME INPUTS
# ============================================================

st.subheader("Halftime match situation")

home_name = st.text_input(
    "Home team",
    value="Home",
)

away_name = st.text_input(
    "Away team",
    value="Away",
)

col1, col2 = st.columns(2)

with col1:

    home_goals = st.number_input(
        f"{home_name} HT goals",
        min_value=0,
        max_value=10,
        value=0,
    )

    home_xg = st.number_input(
        f"{home_name} HT xG",
        min_value=0.0,
        max_value=10.0,
        value=0.85,
        step=0.05,
    )

with col2:

    away_goals = st.number_input(
        f"{away_name} HT goals",
        min_value=0,
        max_value=10,
        value=1,
    )

    away_xg = st.number_input(
        f"{away_name} HT xG",
        min_value=0.0,
        max_value=10.0,
        value=0.35,
        step=0.05,
    )


tolerance = st.slider(
    "Historical xG similarity",
    min_value=0.10,
    max_value=1.00,
    value=0.30,
    step=0.05,
)

st.caption(
    "Smaller tolerance = more similar matches, "
    "but usually fewer observations."
)


# ============================================================
# HISTORICAL MATCH FILTERING
# ============================================================

sample = comparable_matches(
    matches,
    ht_home=int(home_goals),
    ht_away=int(away_goals),
    home_xg=float(home_xg),
    away_xg=float(away_xg),
    tolerance=float(tolerance),
    before_date=date.today().isoformat(),
)

st.metric(
    "Comparable historical matches",
    len(sample),
)

if len(sample) < 100:
    st.warning(
        "Small historical sample. "
        "Treat these prices with extra caution."
    )

if not sample:
    st.stop()


# ============================================================
# GOALS MARKETS
# ============================================================

st.divider()

st.subheader("⚽ Second-half goals")

goal_markets = [
    (
        "Home scores 2H",
        home_scores_second_half,
    ),
    (
        "Away scores 2H",
        away_scores_second_half,
    ),
    (
        "Home wins 2H",
        home_wins_second_half,
    ),
    (
        "Over 0.5 goals 2H",
        over_goals(0.5),
    ),
    (
        "Over 1.5 goals 2H",
        over_goals(1.5),
    ),
    (
        "Over 2.5 goals 2H",
        over_goals(2.5),
    ),
]

show_markets(
    sample,
    goal_markets,
)


# ============================================================
# CORNERS MARKETS
# ============================================================

st.divider()

st.subheader("🚩 Corners")

corner_markets = [
    (
        "Over 3.5 corners 2H",
        market_over(
            "corners",
            "second_half",
            3.5,
        ),
    ),
    (
        "Over 4.5 corners 2H",
        market_over(
            "corners",
            "second_half",
            4.5,
        ),
    ),
    (
        "Over 5.5 corners 2H",
        market_over(
            "corners",
            "second_half",
            5.5,
        ),
    ),
    (
        "Over 8.5 corners FT",
        market_over(
            "corners",
            "all",
            8.5,
        ),
    ),
    (
        "Over 9.5 corners FT",
        market_over(
            "corners",
            "all",
            9.5,
        ),
    ),
]

show_markets(
    sample,
    corner_markets,
)


# ============================================================
# YELLOW CARD MARKETS
# ============================================================

st.divider()

st.subheader("🟨 Yellow cards")

yellow_markets = [
    (
        "Over 1.5 yellows 2H",
        market_over(
            "yellows",
            "second_half",
            1.5,
        ),
    ),
    (
        "Over 2.5 yellows 2H",
        market_over(
            "yellows",
            "second_half",
            2.5,
        ),
    ),
    (
        "Over 3.5 yellows 2H",
        market_over(
            "yellows",
            "second_half",
            3.5,
        ),
    ),
    (
        "Over 3.5 yellows FT",
        market_over(
            "yellows",
            "all",
            3.5,
        ),
    ),
    (
        "Over 4.5 yellows FT",
        market_over(
            "yellows",
            "all",
            4.5,
        ),
    ),
]

show_markets(
    sample,
    yellow_markets,
)


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "Fair = historical decimal odds | "
    "N = valid historical observations | "
    "⚠️ = fewer than 100 observations"
)

st.caption(
    "Full-time markets are conditional on the "
    "entered halftime score and xG."
)

st.caption(
    "Yellow-card counts are not bookmaker "
    "card-points totals."
)

st.caption(
    "PRO STARLIZARD V2 | Read-only historical pricing | "
    "Existing pricing engine unchanged"
)
