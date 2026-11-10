
"""
PRO STARLIZARD — Unified Pricing Dashboard V1

Mobile-friendly historical pricing interface.
Read-only Supabase access.
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

st.set_page_config(
    page_title="PRO STARLIZARD Unified",
    page_icon="🦎",
    layout="wide",
)

st.title("🦎 PRO STARLIZARD")
st.caption("Unified historical pricing — Goals • Corners • Cards")

st.info(
    "V1 historical probabilities. "
    "These are not yet calibrated predictive prices."
)


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


@st.cache_data(ttl=3600, show_spinner="Loading historical data...")
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

    matches, rejected = build_matches(xg_rows, event_rows)
    return matches, rejected


def show_markets(matches, markets):
    for label, predicate in markets:
        result = price_market(matches, predicate)

        with st.container(border=True):
            st.markdown(f"**{label}**")

            if result is None:
                st.caption("Insufficient priced observations")
                continue

            a, b = st.columns(2)

            a.metric(
                "Probability",
                f"{result['probability']:.1%}",
            )
            b.metric(
                "Historical fair odds",
                f"{result['fair_odds']:.2f}",
            )

            st.caption(
                f"{result['wins']} hits from "
                f"{result['sample']} matches"
            )

            if not result["sufficient_sample"]:
                st.warning("Small historical sample")


try:
    matches, rejected = historical_matches()
except Exception as exc:
    st.error(f"Historical data could not be loaded: {exc}")
    st.stop()


st.success(f"{len(matches):,} historical matches loaded")

st.subheader("Halftime match situation")

home_name = st.text_input("Home team", value="Home")
away_name = st.text_input("Away team", value="Away")

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
    "Historical xG similarity tolerance",
    min_value=0.10,
    max_value=1.00,
    value=0.30,
    step=0.05,
)

st.caption(
    "A smaller tolerance selects more similar matches "
    "but usually reduces the sample size."
)

sample = comparable_matches(
    matches,
    ht_home=int(home_goals),
    ht_away=int(away_goals),
    home_xg=float(home_xg),
    away_xg=float(away_xg),
    tolerance=float(tolerance),
    before_date=date.today().isoformat(),
)

st.metric("Comparable historical matches", len(sample))

if len(sample) < 100:
    st.warning(
        "Fewer than 100 comparable matches. "
        "Treat these results with extra caution."
    )

if not sample:
    st.stop()

st.divider()

st.subheader("⚽ Second-half goals")

show_markets(
    sample,
    [
        ("Home scores in 2H", home_scores_second_half),
        ("Away scores in 2H", away_scores_second_half),
        ("Home wins 2H", home_wins_second_half),
        ("Over 0.5 goals 2H", over_goals(0.5)),
        ("Over 1.5 goals 2H", over_goals(1.5)),
        ("Over 2.5 goals 2H", over_goals(2.5)),
    ],
)

st.divider()

st.subheader("🚩 Corners")

show_markets(
    sample,
    [
        (
            "Over 3.5 corners 2H",
            market_over("corners", "second_half", 3.5),
        ),
        (
            "Over 4.5 corners 2H",
            market_over("corners", "second_half", 4.5),
        ),
        (
            "Over 5.5 corners 2H",
            market_over("corners", "second_half", 5.5),
        ),
        (
            "Over 8.5 corners FT",
            market_over("corners", "all", 8.5),
        ),
        (
            "Over 9.5 corners FT",
            market_over("corners", "all", 9.5),
        ),
    ],
)

st.divider()

st.subheader("🟨 Yellow cards")

show_markets(
    sample,
    [
        (
            "Over 1.5 yellows 2H",
            market_over("yellows", "second_half", 1.5),
        ),
        (
            "Over 2.5 yellows 2H",
            market_over("yellows", "second_half", 2.5),
        ),
        (
            "Over 3.5 yellows 2H",
            market_over("yellows", "second_half", 3.5),
        ),
        (
            "Over 3.5 yellows FT",
            market_over("yellows", "all", 3.5),
        ),
        (
            "Over 4.5 yellows FT",
            market_over("yellows", "all", 4.5),
        ),
    ],
)

st.divider()

st.subheader("Coming next")

st.write(
    "Pre-match pricing, Asian handicaps, Asian totals, "
    "red-card context, team-specific modelling, "
    "market odds comparison and automatic pattern flags."
)

st.caption(
    "Read-only dashboard. No API collection, "
    "database writes or changes to existing pricing."
)
