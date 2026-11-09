
"""
PRO STARLIZARD
Corners & Cards Research Engine V2

Memory-conscious, read-only historical research.
One market at a time.
No StatsAPI requests or database writes.
"""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_quality import MARKETS, _get, _number


st.set_page_config(
    page_title="Scrumpy | Corners & Cards",
    page_icon="🦎",
    layout="wide",
)

st.title("🦎 PRO STARLIZARD")
st.subheader("Corners & Cards Research V2")

st.caption(
    "Verified historical totals | "
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

EXCLUDED_COMPETITIONS = {"comp_6387"}

market_label = st.selectbox(
    "Select market",
    list(MARKET_LABELS.keys()),
)

market = MARKET_LABELS[market_label]
field, verification_flag = MARKETS[market]


def extract_stats(stats):
    values = {}

    for period in ("all", "first_half", "second_half"):
        for side in ("home", "away"):
            values[f"{period}_{side}"] = _number(
                _get(
                    stats,
                    "overview",
                    field,
                    period,
                    side,
                )
            )

    return values


def is_usable(record, values):
    if record["competition_id"] in EXCLUDED_COMPETITIONS:
        return False, False

    if (
        values["all_home"] is None
        or values["all_away"] is None
    ):
        return False, False

    coverage = record["coverage"]
    verified = record["verified"] is True

    if coverage == "full" and verified:
        return True, True

    if coverage == "partial":
        for side in ("home", "away"):
            total = values[f"all_{side}"]
            first = values[f"first_half_{side}"]
            second = values[f"second_half_{side}"]

            if None in (total, first, second):
                return False, False

            if abs(total - first - second) > 0.000001:
                return False, False

        return True, False

    return False, False


@st.cache_data(ttl=3600, show_spinner=False)
def load_competitions():
    db = create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_SECRET_KEY"],
    )

    mapping = {}
    last_id = None

    while True:
        query = (
            db.table("historical_xg")
            .select("match_id,competition_id")
            .order("match_id")
            .limit(500)
        )

        if last_id is not None:
            query = query.gt("match_id", last_id)

        batch = query.execute().data or []

        if not batch:
            break

        for row in batch:
            mapping[row["match_id"]] = row["competition_id"]

        last_id = batch[-1]["match_id"]

        if len(batch) < 500:
            break

    return mapping


def research(selected_market):
    db = create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_SECRET_KEY"],
    )

    competitions = load_competitions()

    rows = []
    last_id = None
    batch_size = 150

    while True:
        query = (
            db.table("historical_match_events")
            .select(
                f"match_id,stats_data,"
                f"timeline_data->{'coverage'},"
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

            competition = competitions.get(match_id)

            if competition is None:
                continue

            stats = record.get("stats_data")
            values = extract_stats(stats)

            record_info = {
                "competition_id": competition,
                "coverage": record.get("coverage"),
                "verified": record.get(
                    verification_flag
                ),
            }

            usable, timing = is_usable(
                record_info, values
            )

            if not usable:
                continue

            row = {
                "competition_id": competition,
                "timing_usable": timing,
                **values,
            }

            row["match_total"] = (
                values["all_home"] + values["all_away"]
            )

            rows.append(row)

        last_id = batch[-1]["match_id"]

        if len(batch) < batch_size:
            break

    return pd.DataFrame(rows)


if st.button("Run historical research", type="primary"):

    with st.spinner("Checking historical records..."):
        try:
            data = research(market)

            if data.empty:
                st.warning(
                    "No eligible historical records found."
                )
                st.stop()

            actual = len(data)
            expected = EXPECTED[market]

            st.subheader("Quality verification")

            col1, col2, col3 = st.columns(3)

            col1.metric("Usable", f"{actual:,}")
            col2.metric("Expected", f"{expected:,}")
            col3.metric(
                "Timing verified",
                f"{int(data['timing_usable'].sum()):,}",
            )

            if actual == expected:
                st.success("Quality benchmark matched!")
            else:
                st.warning(
                    "Match count differs from "
                    "our verified benchmark."
                )

            st.subheader("Historical averages")

            col1, col2, col3 = st.columns(3)

            col1.metric(
                "Match total",
                f"{data['match_total'].mean():.2f}",
            )

            col2.metric(
                "Home average",
                f"{data['all_home'].mean():.2f}",
            )

            col3.metric(
                "Away average",
                f"{data['all_away'].mean():.2f}",
            )

            halves = data.dropna(
                subset=[
                    "first_half_home",
                    "first_half_away",
                    "second_half_home",
                    "second_half_away",
                ]
            )

            st.subheader("Half-time distributions")

            st.metric(
                "Matches with both halves",
                f"{len(halves):,}",
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

                col1, col2 = st.columns(2)

                col1.metric(
                    "First-half average",
                    f"{first.mean():.2f}",
                )

                col2.metric(
                    "Second-half average",
                    f"{second.mean():.2f}",
                )

            st.subheader("Competition breakdown")

            summary = (
                data.groupby("competition_id")
                .agg(
                    matches=("match_total", "count"),
                    avg_total=("match_total", "mean"),
                    avg_home=("all_home", "mean"),
                    avg_away=("all_away", "mean"),
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
                "Download summary CSV",
                data=summary.to_csv(index=False),
                file_name=f"scrumpy_{market}_summary.csv",
                mime="text/csv",
            )

            st.caption(
                "Read-only Supabase access. "
                "No prediction or profitability claims."
            )

        except Exception as exc:
            st.error("Research could not complete.")
            st.exception(exc)
