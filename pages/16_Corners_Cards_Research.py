
"""
PRO STARLIZARD
Corners & Cards Research Engine — V1

Read-only historical research.
Uses verified data-quality rules.
No StatsAPI calls or database writes.
"""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_quality import add_quality_columns


st.set_page_config(
    page_title="Scrumpy | Corners & Cards",
    page_icon="🦎",
    layout="wide",
)

st.title("🦎 PRO STARLIZARD")
st.subheader("Corners & Cards Research Engine")
st.caption(
    "Historical research V1 | Verified Supabase data"
)


MARKETS = {
    "Corners": ("corners", "corner_kicks"),
    "Yellow cards": ("yellow_cards", "yellow_cards"),
    "Red cards": ("red_cards", "red_cards"),
}

EXPECTED = {
    "corners": 11309,
    "yellow_cards": 11541,
    "red_cards": 11716,
}


@st.cache_data(ttl=3600, show_spinner=False)
def load_table(table, columns):
    db = create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_SECRET_KEY"],
    )

    records = []
    last_id = None

    while True:
        query = (
            db.table(table)
            .select(columns)
            .order("match_id")
            .limit(500)
        )

        if last_id is not None:
            query = query.gt("match_id", last_id)

        response = query.execute()
        batch = response.data or []

        if not batch:
            break

        records.extend(batch)
        last_id = batch[-1]["match_id"]

        if len(batch) < 500:
            break

    return pd.DataFrame(records)


@st.cache_data(ttl=3600, show_spinner=False)
def load_history():
    xg = load_table(
        "historical_xg",
        "match_id,competition_id,match_date",
    )

    events = load_table(
        "historical_match_events",
        "match_id,stats_data,timeline_data,"
        "corners_match,yellow_cards_match,"
        "red_cards_match",
    )

    if xg.empty or events.empty:
        raise ValueError("No historical records returned.")

    if (
        xg["match_id"].duplicated().any()
        or events["match_id"].duplicated().any()
    ):
        raise ValueError(
            "Duplicate match IDs found. "
            "Research stopped to prevent double counting."
        )

    df = xg.merge(
        events,
        on="match_id",
        how="inner",
        validate="one_to_one",
    )

    return add_quality_columns(
        df,
        markets=(
            "corners",
            "yellow_cards",
            "red_cards",
        ),
    )


def stat_value(stats, field, period, side):
    if not isinstance(stats, dict):
        return None

    overview = stats.get("overview", {})
    if not isinstance(overview, dict):
        return None

    market = overview.get(field, {})
    if not isinstance(market, dict):
        return None

    period_data = market.get(period, {})
    if not isinstance(period_data, dict):
        return None

    value = period_data.get(side)

    if value is None or isinstance(value, bool):
        return None

    try:
        number = float(value)
        if not pd.notna(number):
            return None
        return number
    except (TypeError, ValueError):
        return None


def prepare_market(df, market, field):
    eligible = df[
        df[f"{market}_totals_usable"]
    ].copy()

    eligible["match_date"] = pd.to_datetime(
        eligible["match_date"],
        errors="coerce",
    )

    for period in ("all", "first_half", "second_half"):
        for side in ("home", "away"):
            column = f"{period}_{side}"

            eligible[column] = eligible[
                "stats_data"
            ].apply(
                lambda stats: stat_value(
                    stats, field, period, side
                )
            )

    eligible = eligible.dropna(
        subset=["all_home", "all_away"]
    ).copy()

    eligible["match_total"] = (
        eligible["all_home"] + eligible["all_away"]
    )

    eligible["first_half_total"] = (
        eligible["first_half_home"]
        + eligible["first_half_away"]
    )

    eligible["second_half_total"] = (
        eligible["second_half_home"]
        + eligible["second_half_away"]
    )

    return eligible


try:
    with st.spinner("Loading historical records..."):
        history = load_history()

    st.success("Connected to Supabase successfully!")

    st.metric(
        "Historical matches loaded",
        f"{len(history):,}",
    )

    st.divider()

    selection = st.selectbox(
        "Select research market",
        list(MARKETS.keys()),
    )

    market, field = MARKETS[selection]

    data = prepare_market(
        history, market, field
    )

    expected = EXPECTED[market]
    actual = len(data)

    st.subheader("Data quality")

    col1, col2, col3 = st.columns(3)

    col1.metric("Usable matches", f"{actual:,}")
    col2.metric("Expected", f"{expected:,}")
    col3.metric(
        "Coverage",
        f"{actual / 11745 * 100:.1f}%",
    )

    if actual == expected:
        st.success(
            "Quality benchmark matched."
        )
    else:
        st.warning(
            "Match count differs from the "
            "previous verified audit."
        )

    st.subheader("Historical averages")

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Average match total",
        f"{data['match_total'].mean():.2f}",
    )

    col2.metric(
        "Average home team",
        f"{data['all_home'].mean():.2f}",
    )

    col3.metric(
        "Average away team",
        f"{data['all_away'].mean():.2f}",
    )

    st.subheader("First-half / second-half totals")

    halves = data.dropna(
        subset=[
            "first_half_total",
            "second_half_total",
        ]
    )

    st.metric(
        "Matches with both halves available",
        f"{len(halves):,}",
    )

    if not halves.empty:
        col1, col2 = st.columns(2)

        col1.metric(
            "Average first half",
            f"{halves['first_half_total'].mean():.2f}",
        )

        col2.metric(
            "Average second half",
            f"{halves['second_half_total'].mean():.2f}",
        )

    st.subheader("Competition breakdown")

    summary = (
        data.groupby("competition_id")
        .agg(
            matches=("match_id", "count"),
            avg_total=("match_total", "mean"),
            avg_home=("all_home", "mean"),
            avg_away=("all_away", "mean"),
        )
        .reset_index()
    )

    for column in (
        "avg_total",
        "avg_home",
        "avg_away",
    ):
        summary[column] = summary[column].round(2)

    st.dataframe(
        summary,
        hide_index=True,
        use_container_width=True,
    )

    st.subheader("Historical total distribution")

    distribution = (
        data["match_total"]
        .value_counts()
        .sort_index()
        .rename_axis("Match total")
        .reset_index(name="Matches")
    )

    st.dataframe(
        distribution,
        hide_index=True,
        use_container_width=True,
    )

    st.download_button(
        "Download competition summary",
        data=summary.to_csv(index=False),
        file_name=(
            f"scrumpy_{market}_summary.csv"
        ),
        mime="text/csv",
    )

    st.caption(
        "Research only. No prediction or "
        "profitability claims. "
        "Read-only Supabase access."
    )

except Exception as exc:
    st.error("Research engine could not load.")
    st.exception(exc)
