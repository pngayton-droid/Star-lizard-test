
"""
PRO STARLIZARD V5.7
Halftime corners and yellow-card pricing.

New, independent module.
Does not modify V5.6, existing database tables,
historical research or live fixture modules.

Uses VERIFIED historical first-half market totals.
Historical conditional frequencies are NOT
calibrated betting probabilities.
"""

from datetime import date

import pandas as pd
import streamlit as st

from starlizard_unified_pricing import (
    load_table,
    build_matches,
    comparable_matches,
)


MIN_SAMPLE = 30


@st.cache_resource(ttl=3600, show_spinner=False)
def load_market_history(_db):
    xg = load_table(
        _db,
        "historical_xg",
        "match_id,match_date,competition_id,"
        "home_ht_goals,away_ht_goals,"
        "home_goals,away_goals,"
        "home_ht_xg,away_ht_xg",
    )

    events = load_table(
        _db,
        "historical_match_events",
        "match_id,stats_data",
    )

    return build_matches(xg, events)


def market_records(matches, attribute):
    """
    Only accept internally consistent market records.
    """
    result = []

    for match in matches:
        data = getattr(match, attribute)

        if not data.get("valid"):
            continue

        first = data.get("first_half")
        second = data.get("second_half")
        total = data.get("all")

        if any(x is None for x in (first, second, total)):
            continue

        result.append({
            "match": match,
            "first": int(first),
            "second": int(second),
            "total": int(total),
        })

    return result


def select_similar(records, halftime_total, tolerance):
    """
    Match the observed first-half market total.

    No fallback to unmatched matches: that would
    silently remove the requested conditioning.
    """
    return [
        row for row in records
        if abs(row["first"] - halftime_total) <= tolerance
    ]


def estimate_over(records, line, period):
    if not records:
        return None

    wins = sum(
        row[period] > line
        for row in records
    )

    n = len(records)
    p = wins / n

    return {
        "wins": wins,
        "sample": n,
        "probability": p,
        "fair_odds": 1 / p if p > 0 else None,
    }


def compact_market(label, result):
    with st.container(border=True):
        st.markdown(f"**{label}**")

        if result is None:
            st.caption("No verified observations")
            return

        n = result["sample"]

        if n < MIN_SAMPLE:
            st.warning(
                f"Only {n} comparable matches. "
                "Price withheld."
            )
            return

        a, b = st.columns(2)

        a.metric(
            "Historical frequency",
            f'{result["probability"]:.1%}',
        )

        b.metric(
            "Indicative fair odds",
            (
                f'{result["fair_odds"]:.2f}'
                if result["fair_odds"] is not None
                else "—"
            ),
        )

        st.caption(
            f'{result["wins"]}/{n} historical hits'
        )


def display_market_section(
    matches,
    attribute,
    heading,
    first_half_total,
    tolerance,
    second_half_lines,
    full_time_lines,
):
    st.subheader(heading)

    valid = market_records(matches, attribute)

    selected = select_similar(
        valid,
        first_half_total,
        tolerance,
    )

    st.caption(
        f"{len(selected)} matching historical records "
        f"from {len(valid)} verified market records."
    )

    if len(selected) < MIN_SAMPLE:
        st.warning(
            "Insufficient matched observations. "
            "Try widening the first-half tolerance "
            "or the xG comparison tolerance."
        )

    st.markdown("**Second-half markets**")

    for line in second_half_lines:
        result = estimate_over(
            selected,
            line,
            "second",
        )

        compact_market(
            f"Over {line:.1f} second-half "
            + (
                "corners"
                if attribute == "corners"
                else "yellow cards"
            ),
            result,
        )

    st.markdown("**Full-match markets**")

    for line in full_time_lines:
        result = estimate_over(
            selected,
            line,
            "total",
        )

        compact_market(
            f"Over {line:.1f} full-match "
            + (
                "corners"
                if attribute == "corners"
                else "yellow cards"
            ),
            result,
        )


def render_halftime_markets(db):
    st.header("🦎 V5.7 Halftime Market Pricing")

    st.caption(
        "Historical comparisons conditioned on "
        "halftime score, xG, corners and cards."
    )

    try:
        with st.spinner("Loading verified historical data..."):
            matches, rejected = load_market_history(db)
    except Exception as exc:
        st.error(
            f"Could not load historical data: {exc}"
        )
        return

    st.caption(
        f"{len(matches):,} score-valid historical matches."
    )

    st.markdown("**Halftime score**")

    c1, c2 = st.columns(2)

    with c1:
        home_goals = st.number_input(
            "Home HT goals",
            min_value=0,
            max_value=15,
            value=0,
            key="v57_hg",
        )

        home_xg = st.number_input(
            "Home HT xG",
            min_value=0.0,
            max_value=10.0,
            value=0.85,
            step=0.05,
            key="v57_hxg",
        )

    with c2:
        away_goals = st.number_input(
            "Away HT goals",
            min_value=0,
            max_value=15,
            value=1,
            key="v57_ag",
        )

        away_xg = st.number_input(
            "Away HT xG",
            min_value=0.0,
            max_value=10.0,
            value=0.35,
            step=0.05,
            key="v57_axg",
        )

    st.markdown("**Halftime corners**")

    c1, c2 = st.columns(2)

    with c1:
        home_corners = st.number_input(
            "Home corners",
            min_value=0,
            max_value=30,
            value=3,
            key="v57_hc",
        )

    with c2:
        away_corners = st.number_input(
            "Away corners",
            min_value=0,
            max_value=30,
            value=2,
            key="v57_ac",
        )

    st.markdown("**Halftime yellow cards**")

    c1, c2 = st.columns(2)

    with c1:
        home_yellows = st.number_input(
            "Home yellows",
            min_value=0,
            max_value=20,
            value=1,
            key="v57_hy",
        )

    with c2:
        away_yellows = st.number_input(
            "Away yellows",
            min_value=0,
            max_value=20,
            value=2,
            key="v57_ay",
        )

    with st.expander("Historical matching settings"):
        xg_tolerance = st.slider(
            "Halftime xG tolerance",
            min_value=0.10,
            max_value=1.00,
            value=0.30,
            step=0.05,
            key="v57_xgt",
        )

        corner_tolerance = st.slider(
            "Halftime corner tolerance",
            min_value=0,
            max_value=5,
            value=2,
            key="v57_ct",
        )

        yellow_tolerance = st.slider(
            "Halftime yellow-card tolerance",
            min_value=0,
            max_value=4,
            value=1,
            key="v57_yt",
        )

        fixture_date = st.date_input(
            "Fixture date",
            value=date.today(),
            key="v57_date",
        )

    sample = comparable_matches(
        matches,
        ht_home=int(home_goals),
        ht_away=int(away_goals),
        home_xg=float(home_xg),
        away_xg=float(away_xg),
        tolerance=float(xg_tolerance),
        before_date=fixture_date.isoformat(),
    )

    st.divider()

    st.metric(
        "Score and xG comparables",
        len(sample),
    )

    st.caption(
        "Corner and card filters are applied "
        "separately to this sample. "
        "This avoids unnecessarily filtering "
        "corner prices by yellow cards, "
        "or card prices by corners."
    )

    display_market_section(
        matches=sample,
        attribute="corners",
        heading="🚩 Corner fair prices",
        first_half_total=(
            int(home_corners) + int(away_corners)
        ),
        tolerance=corner_tolerance,
        second_half_lines=[3.5, 4.5, 5.5, 6.5],
        full_time_lines=[7.5, 8.5, 9.5, 10.5, 11.5],
    )

    st.divider()

    display_market_section(
        matches=sample,
        attribute="yellows",
        heading="🟨 Yellow-card fair prices",
        first_half_total=(
            int(home_yellows) + int(away_yellows)
        ),
        tolerance=yellow_tolerance,
        second_half_lines=[1.5, 2.5, 3.5, 4.5],
        full_time_lines=[3.5, 4.5, 5.5, 6.5],
    )

    st.divider()

    st.info(
        "These are historical conditional frequencies, "
        "not validated live betting probabilities. "
        "No bookmaker margin, referee adjustment, "
        "team-specific corner/card adjustment, "
        "or market-odds comparison is applied."
    )
