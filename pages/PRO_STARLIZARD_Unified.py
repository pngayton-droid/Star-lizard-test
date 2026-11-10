
"""
PRO STARLIZARD — Unified Dashboard V3

Compact mobile-first pricing dashboard.
All historical markets in one non-scrolling table.

Uses existing unified historical pricing engine.
Read-only Supabase access.
"""

import os
from datetime import date
from html import escape

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
    page_title="PRO STARLIZARD",
    page_icon="🦎",
    layout="wide",
    initial_sidebar_state="collapsed",
)


st.markdown(
    """
<style>
.block-container {
    padding: 0.7rem 0.55rem 2rem;
    max-width: 1000px;
}

h1 {
    font-size: 1.45rem !important;
    margin: 0 !important;
    padding: 0 !important;
}

h2, h3 {
    font-size: 1rem !important;
    padding-top: 0.5rem !important;
}

div[data-testid="stAlert"] {
    padding: 0.4rem 0.6rem;
}

div[data-testid="stMetricValue"] {
    font-size: 1.3rem;
}

div[data-testid="stVerticalBlock"] {
    gap: 0.45rem;
}

.starlizard-table {
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
    font-size: 12px;
    line-height: 1.3;
}

.starlizard-table th {
    text-align: left;
    padding: 7px 3px;
    border-bottom: 2px solid #777;
    font-weight: 700;
}

.starlizard-table td {
    padding: 7px 3px;
    border-bottom: 1px solid rgba(128,128,128,0.25);
    overflow-wrap: break-word;
}

.starlizard-table th:nth-child(1),
.starlizard-table td:nth-child(1) {
    width: 51%;
}

.starlizard-table th:nth-child(2),
.starlizard-table td:nth-child(2) {
    width: 18%;
    text-align: right;
}

.starlizard-table th:nth-child(3),
.starlizard-table td:nth-child(3) {
    width: 17%;
    text-align: right;
}

.starlizard-table th:nth-child(4),
.starlizard-table td:nth-child(4) {
    width: 14%;
    text-align: right;
}

.starlizard-section td {
    font-weight: 700;
    padding-top: 12px;
    padding-bottom: 5px;
    background: rgba(128,128,128,0.09);
}

.starlizard-fair {
    font-weight: 700;
}

.starlizard-small {
    font-size: 11px;
    opacity: 0.8;
}

@media (max-width: 400px) {
    .starlizard-table {
        font-size: 11px;
    }

    .starlizard-table td,
    .starlizard-table th {
        padding-left: 2px;
        padding-right: 2px;
    }
}
</style>
""",
    unsafe_allow_html=True,
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
        raise RuntimeError("Supabase credentials missing")

    return create_client(url, key)


@st.cache_data(ttl=3600, show_spinner="Loading history...")
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

    return build_matches(xg_rows, event_rows)


def markets():
    return [
        ("⚽ Goals", None),
        ("Home scores 2H", home_scores_second_half),
        ("Away scores 2H", away_scores_second_half),
        ("Home wins 2H", home_wins_second_half),
        ("Over 0.5 goals 2H", over_goals(0.5)),
        ("Over 1.5 goals 2H", over_goals(1.5)),
        ("Over 2.5 goals 2H", over_goals(2.5)),

        ("🚩 Corners", None),
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

        ("🟨 Yellow cards", None),
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
    ]


def render_compact_table(sample):
    html = [
        '<table class="starlizard-table">',
        "<thead><tr>",
        "<th>Market</th>",
        "<th>Prob.</th>",
        "<th>Fair</th>",
        "<th>N</th>",
        "</tr></thead><tbody>",
    ]

    for label, predicate in markets():
        if predicate is None:
            html.append(
                '<tr class="starlizard-section">'
                f'<td colspan="4">{escape(label)}</td>'
                "</tr>"
            )
            continue

        result = price_market(sample, predicate)

        if result is None:
            probability = "—"
            fair = "—"
            count = "0"
        else:
            probability = f"{result['probability']:.1%}"
            fair = f"{result['fair_odds']:.2f}"
            count = str(result["sample"])

            if not result["sufficient_sample"]:
                label += " ⚠️"

        html.append(
            "<tr>"
            f"<td>{escape(label)}</td>"
            f"<td>{probability}</td>"
            f'<td class="starlizard-fair">{fair}</td>'
            f"<td>{count}</td>"
            "</tr>"
        )

    html.append("</tbody></table>")

    st.markdown(
        "\n".join(html),
        unsafe_allow_html=True,
    )


st.title("🦎 PRO STARLIZARD")
st.caption("Unified historical pricing • Mobile V3")

try:
    matches, rejected = historical_matches()
except Exception as exc:
    st.error(f"Could not load historical data: {exc}")
    st.stop()

st.caption(f"Database: {len(matches):,} historical matches")

st.subheader("Halftime inputs")

with st.container():
    names = st.columns(2)

    with names[0]:
        home_name = st.text_input(
            "Home",
            value="Home",
        )

    with names[1]:
        away_name = st.text_input(
            "Away",
            value="Away",
        )

    scores = st.columns(2)

    with scores[0]:
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

    with scores[1]:
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

with st.expander("Advanced historical filters"):
    tolerance = st.slider(
        "xG similarity tolerance",
        min_value=0.10,
        max_value=1.00,
        value=0.30,
        step=0.05,
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

st.markdown(
    f"**{home_name} {home_goals}–{away_goals} "
    f"{away_name}** · "
    f"HT xG {home_xg:.2f}–{away_xg:.2f} · "
    f"**{len(sample)} matches**"
)

if len(sample) < 100:
    st.warning(
        "Small sample: historical estimates may be unstable."
    )

if not sample:
    st.stop()

st.subheader("Market pricing")

render_compact_table(sample)

st.markdown(
    '<p class="starlizard-small">'
    "Fair = historical decimal odds. "
    "N = valid observations. "
    "⚠️ = fewer than 100 matches. "
    "FT markets are conditional on the halftime state."
    "</p>",
    unsafe_allow_html=True,
)

st.caption(
    "Historical frequencies, not calibrated predictions. "
    "Yellow cards are not bookmaker card points. "
    "Existing pricing engine unchanged."
)
