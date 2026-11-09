
"""
PRO STARLIZARD
Corners & Cards Research V2.2

Read-only historical research with match context.
Preserves V2.1 quality and half-integrity rules.
"""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_quality import (
    MARKETS,
    _get,
    _number,
    classify_match,
)

st.set_page_config(
    page_title="Scrumpy | Corners & Cards",
    page_icon="🦎",
    layout="wide",
)

st.title("🦎 PRO STARLIZARD")
st.subheader("Corners & Cards Research V2.2")

st.caption(
    "Verified historical data | Match context | "
    "Read-only Supabase research"
)

MARKET_LABELS = {
    "Corners": "corners",
    "Yellow cards": "yellow_cards",
    "Red cards": "red_cards",
}

EXPECTED = {
    "corners": 11309,
    "yellow_cards": 11541,
    "red_cards": 11716,
}

market_label = st.selectbox(
    "Select market",
    list(MARKET_LABELS),
)
market = MARKET_LABELS[market_label]

field, verification_flag = MARKETS[market]


def database():
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_SECRET_KEY"],
    )


def extract_stats(stats):
    values = {}

    for period in ("all", "first_half", "second_half"):
        for side in ("home", "away"):
            values[f"{period}_{side}"] = _number(
                _get(
                    stats, "overview", field, period, side
                )
            )

    return values


def consistent_halves(values):
    for side in ("home", "away"):
        total = values[f"all_{side}"]
        first = values[f"first_half_{side}"]
        second = values[f"second_half_{side}"]

        if None in (total, first, second):
            return False

        if abs(total - first - second) > 0.000001:
            return False

    return True


@st.cache_data(ttl=3600, show_spinner=False)
def load_match_context():
    db = database()
    context = {}
    last_id = None

    columns = (
        "match_id,match_date,competition_id,"
        "home_team,away_team,"
        "home_goals,away_goals,"
        "home_ht_goals,away_ht_goals,"
        "home_xg,away_xg,"
        "home_ht_xg,away_ht_xg"
    )

    while True:
        query = (
            db.table("historical_xg")
            .select(columns)
            .order("match_id")
            .limit(500)
        )

        if last_id is not None:
            query = query.gt("match_id", last_id)

        batch = query.execute().data or []

        if not batch:
            break

        for record in batch:
            context[record["match_id"]] = record

        last_id = batch[-1]["match_id"]

        if len(batch) < 500:
            break

    return context


def research(selected_market):
    db = database()
    context = load_match_context()

    rows = []
    last_id = None
    batch_size = 150

    while True:
        query = (
            db.table("historical_match_events")
            .select(
                "match_id,stats_data,"
                "timeline_data->>coverage,"
                f"{verification_flag}"
            )
            .order("match_id")
            .limit(batch_size)
        )

        if last_id is not None:
            query = query.gt("match_id", last_id)

        batch = query.execute().data or []

        if not batch:
            break

        for record in batch:
            match_id = record["match_id"]
            match = context.get(match_id)

            if match is None:
                continue

            stats = record.get("stats_data")
            values = extract_stats(stats)

            quality_record = {
                "competition_id": match["competition_id"],
                "stats_data": stats,
                "timeline_data": {
                    "coverage": record.get("coverage")
                },
                verification_flag: record.get(
                    verification_flag
                ),
            }

            quality = classify_match(
                quality_record, selected_market
            )

            if quality not in (
                "timeline_verified",
                "partial_totals_only",
            ):
                continue

            half_valid = consistent_halves(values)

            home_ht = match.get("home_ht_goals")
            away_ht = match.get("away_ht_goals")

            if home_ht is None or away_ht is None:
                ht_situation = "Unknown"
            elif home_ht > away_ht:
                ht_situation = "Home leading"
            elif home_ht < away_ht:
                ht_situation = "Away leading"
            else:
                ht_situation = "Level"

            row = {
                **match,
                **values,
                "quality": quality,
                "timing_usable": (
                    quality == "timeline_verified"
                ),
                "halves_consistent": half_valid,
                "ht_situation": ht_situation,
                "match_total": (
                    values["all_home"] + values["all_away"]
                ),
            }

            rows.append(row)

        last_id = batch[-1]["match_id"]

        if len(batch) < batch_size:
            break

    return pd.DataFrame(rows)


if st.button("Run historical research", type="primary"):
    with st.spinner("Researching historical matches..."):
        try:
            data = research(market)

            if data.empty:
                st.warning("No eligible matches found.")
                st.stop()

            actual = len(data)
            expected = EXPECTED[market]

            st.subheader("Quality verification")

            a, b, c = st.columns(3)

            a.metric("Usable matches", f"{actual:,}")
            b.metric("Expected", f"{expected:,}")
            c.metric(
                "Timing verified",
                f"{int(data['timing_usable'].sum()):,}",
            )

            if actual == expected:
                st.success("Full-match benchmark matched.")
            else:
                st.error(
                    "Full-match benchmark differs. "
                    "Investigate before using results."
                )

            st.subheader("Half-by-half integrity")

            valid = int(data["halves_consistent"].sum())
            excluded = actual - valid

            a, b = st.columns(2)
            a.metric("Consistent halves", f"{valid:,}")
            b.metric(
                "Excluded from half analysis",
                f"{excluded:,}",
            )

            halves = data.loc[
                data["halves_consistent"]
            ]

            st.subheader("Historical averages")

            a, b, c = st.columns(3)
            a.metric(
                "Match total",
                f"{data['match_total'].mean():.2f}",
            )
            b.metric(
                "Home average",
                f"{data['all_home'].mean():.2f}",
            )
            c.metric(
                "Away average",
                f"{data['all_away'].mean():.2f}",
            )

            if not halves.empty:
                first = (
                    halves["first_half_home"]
                    + halves["first_half_away"]
                )
                second = (
                    halves["second_half_home"]
                    + halves["second_half_away"]
                )

                a, b = st.columns(2)
                a.metric(
                    "First-half average",
                    f"{first.mean():.2f}",
                )
                b.metric(
                    "Second-half average",
                    f"{second.mean():.2f}",
                )

            st.subheader("Match context coverage")

            required_context = [
                "match_date",
                "home_team",
                "away_team",
                "home_goals",
                "away_goals",
                "home_ht_goals",
                "away_ht_goals",
                "home_xg",
                "away_xg",
                "home_ht_xg",
                "away_ht_xg",
            ]

            context_complete = data[
                required_context
            ].notna().all(axis=1)

            a, b = st.columns(2)
            a.metric(
                "Complete context",
                f"{int(context_complete.sum()):,}",
            )
            b.metric(
                "Incomplete context",
                f"{int((~context_complete).sum()):,}",
            )

            st.subheader("Half-time match situations")

            situations = (
                data.groupby("ht_situation")
                .agg(
                    matches=("match_id", "count"),
                    avg_total=("match_total", "mean"),
                    consistent_halves=(
                        "halves_consistent", "sum"
                    ),
                )
                .round(2)
                .reset_index()
            )

            st.dataframe(
                situations,
                hide_index=True,
                width="stretch",
            )

            st.subheader("Competition breakdown")

            summary = (
                data.groupby("competition_id")
                .agg(
                    matches=("match_id", "count"),
                    avg_total=("match_total", "mean"),
                    avg_home=("all_home", "mean"),
                    avg_away=("all_away", "mean"),
                    consistent_halves=(
                        "halves_consistent", "sum"
                    ),
                )
                .round(2)
                .reset_index()
            )

            st.dataframe(
                summary,
                hide_index=True,
                width="stretch",
            )

            st.download_button(
                "Download competition summary CSV",
                data=summary.to_csv(index=False),
                file_name=f"scrumpy_{market}_summary.csv",
                mime="text/csv",
            )

            st.download_button(
                "Download match-level research CSV",
                data=data.to_csv(index=False),
                file_name=f"scrumpy_{market}_matches.csv",
                mime="text/csv",
            )

            st.caption(
                "Historical research only. "
                "No Supabase records modified."
            )

        except Exception as exc:
            st.error("Research could not complete.")
            st.exception(exc)
