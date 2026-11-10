
"""PRO STARLIZARD — Unified Dashboard V4.

Pre-match team pricing plus historical halftime markets.
Read-only Supabase access. No TheStatsAPI calls.
"""

import os
from datetime import date
from html import escape

import streamlit as st
from supabase import create_client

from starlizard_pricing_engine import (
    load_historical_xg,
    fit_ratings,
    price_fixture,
    asian_market,
)
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

st.markdown("""
<style>
.block-container {
    padding: 0.8rem 0.6rem 2rem;
    max-width: 1000px;
}
h1 {font-size:1.5rem!important}
h2,h3 {font-size:1.1rem!important}
.sl-table {
    width:100%;
    table-layout:fixed;
    border-collapse:collapse;
    font-size:12px;
    line-height:1.3;
}
.sl-table th,.sl-table td {
    padding:7px 3px;
    border-bottom:1px solid rgba(128,128,128,.25);
    overflow-wrap:break-word;
}
.sl-table th:first-child,
.sl-table td:first-child {width:51%;text-align:left}
.sl-table th:nth-child(2),
.sl-table td:nth-child(2) {width:18%;text-align:right}
.sl-table th:nth-child(3),
.sl-table td:nth-child(3) {width:17%;text-align:right}
.sl-table th:nth-child(4),
.sl-table td:nth-child(4) {width:14%;text-align:right}
.sl-section td {
    font-weight:700;
    background:rgba(128,128,128,.10);
    padding-top:11px;
}
@media(max-width:400px){
    .sl-table {font-size:11px}
    .sl-table td,.sl-table th {padding:6px 2px}
}
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def database():
    url = st.secrets.get("SUPABASE_URL") or os.getenv(
        "SUPABASE_URL"
    )
    key = st.secrets.get("SUPABASE_SECRET_KEY") or os.getenv(
        "SUPABASE_SECRET_KEY"
    )
    if not url or not key:
        raise RuntimeError("Supabase credentials are missing")
    return create_client(url, key)


@st.cache_data(ttl=3600, show_spinner="Loading fixtures...")
def fixture_catalogue():
    db = database()
    rows = load_table(
        db,
        "historical_xg",
        "match_id,competition_id,match_date,"
        "home_team,away_team",
    )
    catalogue = {}
    for row in rows:
        competition = str(
            row.get("competition_id") or ""
        ).strip()
        home = str(row.get("home_team") or "").strip()
        away = str(row.get("away_team") or "").strip()
        if not competition or not home or not away:
            continue
        if home == away:
            continue
        catalogue.setdefault(competition, set()).update(
            (home, away)
        )
    return {
        competition: sorted(teams)
        for competition, teams in sorted(catalogue.items())
    }


@st.cache_data(ttl=3600, show_spinner="Training team ratings...")
def trained_ratings(competition, cutoff, half_life, ridge):
    history = load_historical_xg(
        database(), competition, cutoff
    )
    ratings = fit_ratings(
        history,
        competition,
        cutoff,
        half_life_days=half_life,
        ridge=ridge,
        minimum_matches=60,
    )
    return ratings


@st.cache_data(ttl=3600, show_spinner="Loading match history...")
def historical_matches():
    db = database()
    xg = load_table(
        db,
        "historical_xg",
        "match_id,match_date,competition_id,"
        "home_ht_goals,away_ht_goals,"
        "home_goals,away_goals,"
        "home_ht_xg,away_ht_xg",
    )
    events = load_table(
        db,
        "historical_match_events",
        "match_id,stats_data",
    )
    return build_matches(xg, events)


def compact_table(rows):
    html = [
        '<table class="sl-table"><thead><tr>',
        "<th>Market</th><th>Prob.</th>",
        "<th>Fair</th><th>N</th>",
        "</tr></thead><tbody>",
    ]
    for label, probability, fair, sample in rows:
        if probability is None and fair is None:
            html.append(
                '<tr class="sl-section"><td colspan="4">'
                + escape(str(label)) + "</td></tr>"
            )
            continue
        p = "—" if probability is None else f"{probability:.1%}"
        f = "—" if fair is None else f"{fair:.2f}"
        n = "—" if sample is None else str(sample)
        html.append(
            "<tr>"
            f"<td>{escape(str(label))}</td>"
            f"<td>{p}</td><td><b>{f}</b></td>"
            f"<td>{n}</td></tr>"
        )
    html.append("</tbody></table>")
    st.markdown("\n".join(html), unsafe_allow_html=True)


def historical_market_rows(matches):
    groups = [
        ("⚽ Second-half goals", [
            ("Home scores 2H", home_scores_second_half),
            ("Away scores 2H", away_scores_second_half),
            ("Home wins 2H", home_wins_second_half),
            ("Over 0.5 goals 2H", over_goals(0.5)),
            ("Over 1.5 goals 2H", over_goals(1.5)),
            ("Over 2.5 goals 2H", over_goals(2.5)),
        ]),
        ("🚩 Corners", [
            ("Over 3.5 corners 2H",
             market_over("corners", "second_half", 3.5)),
            ("Over 4.5 corners 2H",
             market_over("corners", "second_half", 4.5)),
            ("Over 5.5 corners 2H",
             market_over("corners", "second_half", 5.5)),
            ("Over 8.5 corners FT",
             market_over("corners", "all", 8.5)),
            ("Over 9.5 corners FT",
             market_over("corners", "all", 9.5)),
        ]),
        ("🟨 Yellow cards", [
            ("Over 1.5 yellows 2H",
             market_over("yellows", "second_half", 1.5)),
            ("Over 2.5 yellows 2H",
             market_over("yellows", "second_half", 2.5)),
            ("Over 3.5 yellows 2H",
             market_over("yellows", "second_half", 3.5)),
            ("Over 3.5 yellows FT",
             market_over("yellows", "all", 3.5)),
            ("Over 4.5 yellows FT",
             market_over("yellows", "all", 4.5)),
        ]),
    ]
    rows = []
    for heading, markets in groups:
        rows.append((heading, None, None, None))
        for label, predicate in markets:
            result = price_market(matches, predicate)
            if result is None:
                rows.append((label, None, None, 0))
            else:
                if not result["sufficient_sample"]:
                    label += " ⚠️"
                rows.append((
                    label,
                    result["probability"],
                    result["fair_odds"],
                    result["sample"],
                ))
    return rows


st.title("🦎 PRO STARLIZARD")
st.caption("Unified fixture pricing | Experimental model")

tab_pre, tab_ht = st.tabs([
    "⚽ Pre-match",
    "⏱️ Halftime",
])

with tab_pre:
    st.subheader("Choose fixture")

    try:
        catalogue = fixture_catalogue()
    except Exception as exc:
        st.error(f"Fixture catalogue failed: {exc}")
        catalogue = {}

    if not catalogue:
        st.warning("No usable competitions found.")
    else:
        competition = st.selectbox(
            "Competition ID",
            list(catalogue),
            key="pre_comp",
        )
        available = catalogue[competition]

        if len(available) < 2:
            st.warning("Not enough teams in this competition.")
            st.stop()

        c1, c2 = st.columns(2)
        with c1:
            home = st.selectbox(
                "Home team",
                available,
                key="pre_home",
            )
        with c2:
            away = st.selectbox(
                "Away team",
                available,
                index=1,
                key="pre_away",
            )

        cutoff = st.date_input(
            "Price fixture using data before",
            value=date.today(),
            key="pre_cutoff",
        )

        with st.expander("Rating settings"):
            half_life = st.slider(
                "Recency half-life (days)",
                60, 365, 180, 5,
                key="pre_half_life",
            )
            ridge = st.slider(
                "Rating shrinkage",
                2.0, 30.0, 10.0, 1.0,
                key="pre_ridge",
            )

        if home == away:
            st.warning("Choose two different teams.")
        else:
            try:
                ratings = trained_ratings(
                    competition,
                    cutoff.isoformat(),
                    half_life,
                    ridge,
                )
                priced = price_fixture(ratings, home, away)
            except Exception as exc:
                st.warning(
                    "Could not price this fixture: "
                    f"{exc}"
                )
                priced = None

            if priced:
                st.markdown(f"**{home} v {away}**")
                c1, c2 = st.columns(2)
                with c1:
                    st.metric(
                        "Home expected goals",
                        f"{priced['home_xg']:.2f}",
                    )
                with c2:
                    st.metric(
                        "Away expected goals",
                        f"{priced['away_xg']:.2f}",
                    )

                st.caption(
                    f"{ratings.matches} training matches · "
                    f"{len(ratings.teams)} teams"
                )

                probabilities = priced["probabilities"]
                odds = priced["fair_odds"]

                labels = [
                    ("Home win", "home"),
                    ("Draw", "draw"),
                    ("Away win", "away"),
                    ("Over 2.5 goals", "over_2_5"),
                    ("Under 2.5 goals", "under_2_5"),
                    ("BTTS Yes", "btts_yes"),
                    ("BTTS No", "btts_no"),
                ]

                st.subheader("Pre-match fair odds")
                compact_table([
                    (label, probabilities[key], odds[key], None)
                    for label, key in labels
                ])

                st.subheader("Asian pricing")

                market_options = {
                    "Home handicap": "home_handicap",
                    "Away handicap": "away_handicap",
                    "Over goals": "over_goals",
                    "Under goals": "under_goals",
                }

                market_name = st.selectbox(
                    "Asian market",
                    list(market_options),
                    key="asian_market",
                )
                is_handicap = "handicap" in market_name

                lines = (
                    [i / 4 for i in range(-12, 13)]
                    if is_handicap
                    else [i / 4 for i in range(2, 25)]
                )

                default_line = (
                    0.0 if is_handicap else 2.5
                )

                line = st.selectbox(
                    "Asian line",
                    lines,
                    index=lines.index(default_line),
                    key="asian_line",
                )

                asian = asian_market(
                    priced["matrix"],
                    market_options[market_name],
                    line,
                )

                fair = asian["fair_odds"]
                if fair is None:
                    st.warning("No finite fair price for this line.")
                else:
                    st.metric("Asian fair odds", f"{fair:.3f}")

                    quote = st.number_input(
                        "Bookmaker decimal odds",
                        min_value=1.01,
                        max_value=100.0,
                        value=1.95,
                        step=0.01,
                        key="asian_quote",
                    )

                    roi = (
                        asian["win_units"] * (quote - 1)
                        - asian["loss_units"]
                    )

                    st.metric(
                        "Model-implied ROI",
                        f"{roi:+.2%}",
                    )

                with st.expander("Correct-score prices"):
                    score_rows = []
                    for score, probability in (
                        priced["correct_scores"].items()
                    ):
                        if probability > 0:
                            score_rows.append((
                                score,
                                probability,
                                1 / probability,
                                None,
                            ))
                    compact_table(score_rows)

                st.caption(
                    "Model estimates are experimental. "
                    "Positive model-implied ROI does not "
                    "establish a verified betting edge."
                )

with tab_ht:
    st.subheader("Historical halftime pricing")

    try:
        matches, rejected = historical_matches()
    except Exception as exc:
        st.error(f"Historical data failed: {exc}")
        matches = []

    if matches:
        st.caption(
            f"{len(matches):,} historical matches loaded"
        )

        names = st.columns(2)
        with names[0]:
            ht_home_name = st.text_input(
                "Home",
                value="Home",
                key="ht_home_name",
            )
        with names[1]:
            ht_away_name = st.text_input(
                "Away",
                value="Away",
                key="ht_away_name",
            )

        inputs = st.columns(2)
        with inputs[0]:
            ht_home = st.number_input(
                f"{ht_home_name} HT goals",
                min_value=0,
                max_value=10,
                value=0,
                key="ht_home_goals",
            )
            ht_home_xg = st.number_input(
                f"{ht_home_name} HT xG",
                min_value=0.0,
                max_value=10.0,
                value=0.85,
                step=0.05,
                key="ht_home_xg",
            )

        with inputs[1]:
            ht_away = st.number_input(
                f"{ht_away_name} HT goals",
                min_value=0,
                max_value=10,
                value=1,
                key="ht_away_goals",
            )
            ht_away_xg = st.number_input(
                f"{ht_away_name} HT xG",
                min_value=0.0,
                max_value=10.0,
                value=0.35,
                step=0.05,
                key="ht_away_xg",
            )

        with st.expander("Advanced historical filters"):
            tolerance = st.slider(
                "xG similarity",
                0.10, 1.00, 0.30, 0.05,
                key="ht_tolerance",
            )

        sample = comparable_matches(
            matches,
            ht_home=int(ht_home),
            ht_away=int(ht_away),
            home_xg=float(ht_home_xg),
            away_xg=float(ht_away_xg),
            tolerance=float(tolerance),
            before_date=date.today().isoformat(),
        )

        st.markdown(
            f"**{ht_home_name} {ht_home}–{ht_away} "
            f"{ht_away_name}** · "
            f"**{len(sample)} comparable matches**"
        )

        if len(sample) < 100:
            st.warning("Small historical sample.")

        if sample:
            compact_table(
                historical_market_rows(sample)
            )

        st.caption(
            "Fair = historical decimal odds. "
            "N = valid observations. "
            "⚠️ = fewer than 100 observations."
        )
        st.caption(
            "Halftime results are historical frequencies, "
            "not team-specific calibrated forecasts."
        )

st.divider()
st.caption(
    "PRO STARLIZARD V4 · Read-only Supabase · "
    "Existing pricing engines unchanged"
)
