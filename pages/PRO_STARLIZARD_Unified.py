
"""PRO STARLIZARD V5 — Unified Pricing and Backtesting.

Read-only Supabase.
Existing pricing engines are not modified.
Chronological, out-of-sample evaluation.
"""

import os
import math
from datetime import date
from html import escape

import numpy as np
import pandas as pd
import streamlit as st
from supabase import create_client

from starlizard_pricing_engine import (
    load_historical_xg,
    clean_history,
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

LEAGUE_NAMES = {
    "comp_3039": "Premier League",
    "comp_8321": "Championship",
    "comp_4643": "Bundesliga",
    "comp_0256": "Ligue 1",
    "comp_8531": "Belgian Pro League",
}


def league_label(cid):
    return (
        f"{LEAGUE_NAMES[cid]} ({cid})"
        if cid in LEAGUE_NAMES
        else str(cid)
    )


st.markdown(
    """
<style>
.block-container {
    max-width: 1050px;
    padding: 0.8rem 0.6rem 2rem;
}
h1 {font-size:1.5rem!important}
h2,h3 {font-size:1.1rem!important}
.sl-table {
    width:100%;
    table-layout:fixed;
    border-collapse:collapse;
    font-size:12px;
}
.sl-table th,.sl-table td {
    padding:7px 3px;
    border-bottom:1px solid rgba(128,128,128,.25);
    overflow-wrap:break-word;
}
.sl-table th:first-child,
.sl-table td:first-child {
    width:51%;
    text-align:left;
}
.sl-table th:not(:first-child),
.sl-table td:not(:first-child) {
    text-align:right;
}
.sl-section td {
    font-weight:700;
    background:rgba(128,128,128,.10);
}
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_resource
def database():
    url = (
        st.secrets.get("SUPABASE_URL")
        or os.getenv("SUPABASE_URL")
    )
    key = (
        st.secrets.get("SUPABASE_SECRET_KEY")
        or os.getenv("SUPABASE_SECRET_KEY")
    )
    if not url or not key:
        raise RuntimeError("Missing Supabase credentials")
    return create_client(url, key)


@st.cache_data(ttl=3600)
def fixture_catalogue():
    rows = load_table(
        database(),
        "historical_xg",
        "match_id,competition_id,match_date,"
        "home_team,away_team",
    )
    result = {}
    for row in rows:
        cid = str(row.get("competition_id") or "").strip()
        h = str(row.get("home_team") or "").strip()
        a = str(row.get("away_team") or "").strip()
        if cid and h and a and h != a:
            result.setdefault(cid, set()).update((h, a))
    return {
        cid: sorted(teams)
        for cid, teams in sorted(result.items())
    }


@st.cache_data(ttl=3600)
def trained_ratings(cid, cutoff, half_life, ridge):
    history = load_historical_xg(
        database(), cid, cutoff
    )
    return fit_ratings(
        history,
        cid,
        cutoff,
        half_life_days=half_life,
        ridge=ridge,
        minimum_matches=60,
    )


@st.cache_data(ttl=3600)
def historical_matches():
    xg = load_table(
        database(),
        "historical_xg",
        "match_id,match_date,competition_id,"
        "home_ht_goals,away_ht_goals,"
        "home_goals,away_goals,"
        "home_ht_xg,away_ht_xg",
    )
    events = load_table(
        database(),
        "historical_match_events",
        "match_id,stats_data",
    )
    return build_matches(xg, events)


def compact_table(rows):
    parts = [
        '<table class="sl-table"><thead><tr>',
        "<th>Market</th><th>Prob.</th>",
        "<th>Fair</th><th>N</th>",
        "</tr></thead><tbody>",
    ]
    for label, probability, fair, sample in rows:
        if probability is None and fair is None and sample is None:
            parts.append(
                '<tr class="sl-section"><td colspan="4">'
                + escape(str(label))
                + "</td></tr>"
            )
            continue

        p = "—" if probability is None else f"{probability:.1%}"
        f = "—" if fair is None else f"{fair:.2f}"
        n = "—" if sample is None else str(sample)

        parts.append(
            f"<tr><td>{escape(str(label))}</td>"
            f"<td>{p}</td><td><b>{f}</b></td>"
            f"<td>{n}</td></tr>"
        )

    parts.append("</tbody></table>")
    st.markdown("\n".join(parts), unsafe_allow_html=True)


def historical_market_rows(matches):
    groups = [
        (
            "⚽ Second-half goals",
            [
                ("Home scores 2H", home_scores_second_half),
                ("Away scores 2H", away_scores_second_half),
                ("Home wins 2H", home_wins_second_half),
                ("Over 0.5 goals 2H", over_goals(0.5)),
                ("Over 1.5 goals 2H", over_goals(1.5)),
                ("Over 2.5 goals 2H", over_goals(2.5)),
            ],
        ),
        (
            "🚩 Corners",
            [
                ("Over 3.5 corners 2H", market_over("corners", "second_half", 3.5)),
                ("Over 4.5 corners 2H", market_over("corners", "second_half", 4.5)),
                ("Over 5.5 corners 2H", market_over("corners", "second_half", 5.5)),
                ("Over 8.5 corners FT", market_over("corners", "all", 8.5)),
                ("Over 9.5 corners FT", market_over("corners", "all", 9.5)),
            ],
        ),
        (
            "🟨 Yellow cards",
            [
                ("Over 1.5 yellows 2H", market_over("yellows", "second_half", 1.5)),
                ("Over 2.5 yellows 2H", market_over("yellows", "second_half", 2.5)),
                ("Over 3.5 yellows 2H", market_over("yellows", "second_half", 3.5)),
                ("Over 3.5 yellows FT", market_over("yellows", "all", 3.5)),
                ("Over 4.5 yellows FT", market_over("yellows", "all", 4.5)),
            ],
        ),
    ]

    output = []
    for heading, markets in groups:
        output.append((heading, None, None, None))
        for label, predicate in markets:
            result = price_market(matches, predicate)
            if result is None:
                output.append((label, None, None, 0))
            else:
                if not result["sufficient_sample"]:
                    label += " ⚠️"
                output.append((
                    label,
                    result["probability"],
                    result["fair_odds"],
                    result["sample"],
                ))
    return output


# ============================================================
# BACKTEST ENGINE
# ============================================================

@st.cache_data(ttl=3600, show_spinner="Loading backtest records...")
def backtest_history():
    rows = load_table(
        database(),
        "historical_xg",
        "match_id,competition_id,match_date,"
        "home_team,away_team,home_xg,away_xg,"
        "home_goals,away_goals",
    )

    df = pd.DataFrame(rows)

    if df.empty:
        return pd.DataFrame(), {
            "loaded": 0,
            "eligible": 0,
        }

    loaded = len(df)

    required = [
        "match_id", "competition_id", "match_date",
        "home_team", "away_team", "home_xg", "away_xg",
        "home_goals", "away_goals",
    ]

    df = df.dropna(subset=required).copy()

    df["match_date"] = pd.to_datetime(
        df["match_date"], utc=True, errors="coerce"
    )

    for col in [
        "home_xg", "away_xg",
        "home_goals", "away_goals",
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=required)

    for col in ["home_team", "away_team", "competition_id"]:
        df[col] = df[col].astype(str).str.strip()

    df = df[
        (df.home_team != "")
        & (df.away_team != "")
        & (df.home_team != df.away_team)
        & (df.competition_id != "")
        & (df.home_xg >= 0)
        & (df.away_xg >= 0)
        & np.isfinite(df.home_xg)
        & np.isfinite(df.away_xg)
        & np.isfinite(df.home_goals)
        & np.isfinite(df.away_goals)
        & (df.home_goals >= 0)
        & (df.away_goals >= 0)
        & (df.home_goals % 1 == 0)
        & (df.away_goals % 1 == 0)
    ].copy()

    df = (
        df.drop_duplicates("match_id", keep="last")
        .sort_values(["competition_id", "match_date", "match_id"])
        .reset_index(drop=True)
    )

    return df, {
        "loaded": loaded,
        "eligible": len(df),
    }


def binary_brier(probabilities, outcomes):
    return float(np.mean(
        (np.asarray(probabilities) - np.asarray(outcomes)) ** 2
    ))


def binary_logloss(probabilities, outcomes):
    p = np.clip(np.asarray(probabilities), 1e-12, 1 - 1e-12)
    y = np.asarray(outcomes)
    return float(np.mean(
        -y * np.log(p) - (1 - y) * np.log(1 - p)
    ))


def multiclass_scores(frame, prefix):
    probs = frame[
        [f"{prefix}_home", f"{prefix}_draw", f"{prefix}_away"]
    ].to_numpy(dtype=float)

    outcomes = frame["outcome"].to_numpy(dtype=int)
    actual = np.eye(3)[outcomes]

    brier = float(np.mean(np.sum((probs - actual) ** 2, axis=1)))
    logloss = float(np.mean(
        -np.log(np.clip(probs[np.arange(len(probs)), outcomes], 1e-12, 1))
    ))
    return brier, logloss


def score_summary(frame):
    if frame.empty:
        return None

    model_brier, model_log = multiclass_scores(frame, "model")
    base_brier, base_log = multiclass_scores(frame, "base")

    return {
        "Matches": len(frame),
        "1X2 Brier": round(model_brier, 4),
        "Baseline Brier": round(base_brier, 4),
        "1X2 Log loss": round(model_log, 4),
        "Baseline log loss": round(base_log, 4),
        "O2.5 Brier": round(
            binary_brier(frame.model_over, frame.actual_over), 4
        ),
        "Baseline O2.5": round(
            binary_brier(frame.base_over, frame.actual_over), 4
        ),
        "BTTS Brier": round(
            binary_brier(frame.model_btts, frame.actual_btts), 4
        ),
        "Baseline BTTS": round(
            binary_brier(frame.base_btts, frame.actual_btts), 4
        ),
        "O2.5 Log loss": round(
            binary_logloss(frame.model_over, frame.actual_over), 4
        ),
        "BTTS Log loss": round(
            binary_logloss(frame.model_btts, frame.actual_btts), 4
        ),
    }


def run_backtest(df, periods=6, half_life=180, ridge=10):
    """Expanding-history monthly backtest.

    For each competition, use its last `periods` complete
    calendar months as test windows. Ratings and baseline
    frequencies use matches strictly before each window.
    """

    predictions = []
    audit = []

    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    today = pd.Timestamp.now(tz="UTC").normalize()
    current_month = today.to_period("M")

    # Only complete historical calendar months are tested.
    last_complete = current_month - 1

    competitions = sorted(df.competition_id.unique())

    progress = st.progress(0, text="Running backtest...")

    for ci, cid in enumerate(competitions):
        league = df[df.competition_id == cid].copy()

        total_predicted = 0
        skipped_unseen = 0
        skipped_training = 0
        attempted = 0

        for step in range(periods):
            month = last_complete - (periods - 1 - step)

            cutoff = pd.Timestamp(
                month.start_time
            ).tz_localize("UTC")

            end = pd.Timestamp(
                (month + 1).start_time
            ).tz_localize("UTC")

            train = league[league.match_date < cutoff].copy()
            test = league[
                (league.match_date >= cutoff)
                & (league.match_date < end)
            ].copy()

            if test.empty:
                continue

            attempted += len(test)

            if len(train) < 60:
                skipped_training += len(test)
                continue

            before = cutoff.strftime("%Y-%m-%d")

            training_columns = [
                "match_id", "competition_id", "match_date",
                "home_team", "away_team", "home_xg", "away_xg",
            ]

            try:
                ratings = fit_ratings(
                    train[training_columns],
                    cid,
                    before,
                    half_life_days=half_life,
                    ridge=ridge,
                    minimum_matches=60,
                )
            except (ValueError, np.linalg.LinAlgError):
                skipped_training += len(test)
                continue

            # Smoothed historical-frequency baseline.
            # Only earlier matches in the same competition.
            home_wins = int(
                (train.home_goals > train.away_goals).sum()
            )
            draws = int(
                (train.home_goals == train.away_goals).sum()
            )
            away_wins = int(
                (train.home_goals < train.away_goals).sum()
            )

            n = len(train)

            base_home = (home_wins + 1) / (n + 3)
            base_draw = (draws + 1) / (n + 3)
            base_away = (away_wins + 1) / (n + 3)

            base_over = float(
                ((train.home_goals + train.away_goals >= 3).sum() + 1)
                / (n + 2)
            )

            base_btts = float(
                (((train.home_goals > 0) & (train.away_goals > 0)).sum() + 1)
                / (n + 2)
            )

            known = set(ratings.teams)

            for row in test.itertuples(index=False):
                if row.home_team not in known or row.away_team not in known:
                    skipped_unseen += 1
                    continue

                try:
                    priced = price_fixture(
                        ratings, row.home_team, row.away_team
                    )
                except (ValueError, OverflowError):
                    skipped_unseen += 1
                    continue

                p = priced["probabilities"]

                outcome = (
                    0 if row.home_goals > row.away_goals
                    else 1 if row.home_goals == row.away_goals
                    else 2
                )

                predictions.append({
                    "competition_id": cid,
                    "league": league_label(cid),
                    "month": str(month),
                    "match_id": row.match_id,
                    "match_date": row.match_date,
                    "home_team": row.home_team,
                    "away_team": row.away_team,
                    "outcome": outcome,
                    "model_home": p["home"],
                    "model_draw": p["draw"],
                    "model_away": p["away"],
                    "base_home": base_home,
                    "base_draw": base_draw,
                    "base_away": base_away,
                    "model_over": p["over_2_5"],
                    "base_over": base_over,
                    "actual_over": int(
                        row.home_goals + row.away_goals >= 3
                    ),
                    "model_btts": p["btts_yes"],
                    "base_btts": base_btts,
                    "actual_btts": int(
                        row.home_goals > 0 and row.away_goals > 0
                    ),
                    "training_matches": ratings.matches,
                })

                total_predicted += 1

        audit.append({
            "League": league_label(cid),
            "Eligible in test windows": attempted,
            "Predicted": total_predicted,
            "Insufficient training": skipped_training,
            "Unseen teams / pricing failures": skipped_unseen,
        })

        progress.progress(
            (ci + 1) / len(competitions),
            text=f"Checked {ci + 1}/{len(competitions)} leagues",
        )

    progress.empty()

    return pd.DataFrame(predictions), pd.DataFrame(audit)


def calibration_table(predictions, probability_col, outcome_col):
    rows = []

    for low in np.arange(0, 1, 0.1):
        high = low + 0.1

        if high >= 1:
            part = predictions[
                (predictions[probability_col] >= low)
                & (predictions[probability_col] <= high)
            ]
        else:
            part = predictions[
                (predictions[probability_col] >= low)
                & (predictions[probability_col] < high)
            ]

        if part.empty:
            continue

        rows.append({
            "Predicted band": f"{low:.0%}–{high:.0%}",
            "Matches": len(part),
            "Average prediction": round(
                float(part[probability_col].mean()), 3
            ),
            "Actual frequency": round(
                float(part[outcome_col].mean()), 3
            ),
        })

    return pd.DataFrame(rows)


# ============================================================
# DASHBOARD
# ============================================================

st.title("🦎 PRO STARLIZARD")
st.caption("Unified fixture pricing | V5")

tab_pre, tab_ht, tab_test = st.tabs([
    "⚽ Pre-match",
    "⏱️ Halftime",
    "📊 Backtest",
])


with tab_pre:
    st.subheader("Choose fixture")

    try:
        catalogue = fixture_catalogue()
    except Exception as exc:
        st.error(f"Fixture catalogue failed: {exc}")
        catalogue = {}

    if catalogue:
        competition = st.selectbox(
            "League",
            list(catalogue),
            format_func=league_label,
            key="pre_comp",
        )

        available = catalogue[competition]

        if len(available) >= 2:
            c1, c2 = st.columns(2)

            with c1:
                home = st.selectbox(
                    "Home team", available, key="pre_home"
                )

            with c2:
                away = st.selectbox(
                    "Away team", available,
                    index=1, key="pre_away"
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
                    st.warning(f"Could not price fixture: {exc}")
                    priced = None

                if priced:
                    st.markdown(f"**{home} v {away}**")

                    c1, c2 = st.columns(2)
                    c1.metric(
                        "Home expected goals",
                        f"{priced['home_xg']:.2f}",
                    )
                    c2.metric(
                        "Away expected goals",
                        f"{priced['away_xg']:.2f}",
                    )

                    st.caption(
                        f"{ratings.matches} training matches "
                        f"across {len(ratings.teams)} teams"
                    )

                    p = priced["probabilities"]
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
                        (label, p[key], odds[key], None)
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

                    if is_handicap:
                        lines = [i / 4 for i in range(-12, 13)]
                        default_line = 0.0
                    else:
                        lines = [i / 4 for i in range(2, 25)]
                        default_line = 2.5

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
                        st.warning("No finite fair price.")
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
                        compact_table([
                            (
                                score,
                                probability,
                                1 / probability,
                                None,
                            )
                            for score, probability
                            in priced["correct_scores"].items()
                            if probability > 0
                        ])

                    st.caption(
                        "Experimental probabilities. "
                        "Model-implied ROI is not proven profit."
                    )
        else:
            st.warning("Not enough teams in this competition.")
    else:
        st.warning("No usable competitions found.")


with tab_ht:
    st.subheader("Historical halftime pricing")

    try:
        matches, rejected = historical_matches()
    except Exception as exc:
        st.error(f"Historical data failed: {exc}")
        matches = []

    if matches:
        st.caption(f"{len(matches):,} historical matches loaded")

        c1, c2 = st.columns(2)

        with c1:
            ht_home_name = st.text_input(
                "Home", value="Home", key="ht_home_name"
            )

        with c2:
            ht_away_name = st.text_input(
                "Away", value="Away", key="ht_away_name"
            )

        c1, c2 = st.columns(2)

        with c1:
            ht_home = st.number_input(
                f"{ht_home_name} HT goals",
                0, 10, 0, key="ht_home_goals",
            )
            ht_home_xg = st.number_input(
                f"{ht_home_name} HT xG",
                0.0, 10.0, 0.85, 0.05,
                key="ht_home_xg",
            )

        with c2:
            ht_away = st.number_input(
                f"{ht_away_name} HT goals",
                0, 10, 1, key="ht_away_goals",
            )
            ht_away_xg = st.number_input(
                f"{ht_away_name} HT xG",
                0.0, 10.0, 0.35, 0.05,
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
            compact_table(historical_market_rows(sample))

        st.caption(
            "Historical conditional frequencies. "
            "N = valid observations. "
            "⚠️ = fewer than 100 observations."
        )


with tab_test:
    st.subheader("Historical accuracy backtest")

    st.write(
        "Tests the existing pre-match model against "
        "completed matches it was not trained on."
    )

    st.caption(
        "Each test month uses ratings trained strictly "
        "before that month. All available competitions "
        "are considered. Only complete months are tested."
    )

    periods = st.selectbox(
        "Number of recent complete months",
        [3, 6, 9, 12],
        index=1,
        key="test_periods",
    )

    st.caption(
        "Default model settings: 180-day recency "
        "half-life, 10.0 shrinkage."
    )

    if st.button(
        "Run historical accuracy test",
        type="primary",
        key="run_backtest",
    ):
        try:
            with st.spinner("Preparing historical data..."):
                history, quality = backtest_history()

            st.session_state["backtest_quality"] = quality

            if history.empty:
                st.error("No usable backtest records.")
            else:
                predictions, audit = run_backtest(
                    history,
                    periods=periods,
                    half_life=180,
                    ridge=10,
                )

                st.session_state["backtest_predictions"] = predictions
                st.session_state["backtest_audit"] = audit
                st.session_state["backtest_periods"] = periods

        except Exception as exc:
            st.error(f"Backtest failed: {exc}")

    if "backtest_quality" in st.session_state:
        quality = st.session_state["backtest_quality"]

        st.caption(
            f"Database records: {quality['loaded']:,} · "
            f"Valid xG and final-score records: "
            f"{quality['eligible']:,}"
        )

    if "backtest_predictions" in st.session_state:
        predictions = st.session_state["backtest_predictions"]
        audit = st.session_state["backtest_audit"]

        if predictions.empty:
            st.warning(
                "No matches could be predicted in the "
                "selected test windows. Check the coverage table."
            )
        else:
            st.success(
                f"Completed: {len(predictions):,} "
                "out-of-sample predictions."
            )

            summary = score_summary(predictions)

            st.subheader("Overall results")
            st.dataframe(
                pd.DataFrame([summary]),
                hide_index=True,
                use_container_width=True,
            )

            st.caption(
                "Lower Brier scores and log loss are better. "
                "The baseline uses earlier match-result "
                "frequencies from each league."
            )

            st.subheader("Results by league")

            league_rows = []

            for league, part in predictions.groupby("league"):
                row = score_summary(part)
                row["League"] = league
                league_rows.append(row)

            league_table = pd.DataFrame(league_rows)

            league_table = league_table[
                ["League"] +
                [c for c in league_table.columns if c != "League"]
            ].sort_values("Matches", ascending=False)

            st.dataframe(
                league_table,
                hide_index=True,
                use_container_width=True,
            )

            st.subheader("Probability calibration")

            market = st.selectbox(
                "Calibration market",
                ["Over 2.5 goals", "BTTS Yes"],
                key="calibration_market",
            )

            if market == "Over 2.5 goals":
                probability_col = "model_over"
                outcome_col = "actual_over"
            else:
                probability_col = "model_btts"
                outcome_col = "actual_btts"

            calibration = calibration_table(
                predictions,
                probability_col,
                outcome_col,
            )

            st.dataframe(
                calibration,
                hide_index=True,
                use_container_width=True,
            )

            st.caption(
                "For a well-calibrated model, predictions "
                "averaging 60% should occur about 60% "
                "of the time. Small bins are less reliable."
            )

            st.download_button(
                "Download all backtest predictions",
                predictions.to_csv(index=False),
                file_name="starlizard_backtest_predictions.csv",
                mime="text/csv",
            )

        st.subheader("Coverage and exclusions")

        st.dataframe(
            audit,
            hide_index=True,
            use_container_width=True,
        )

        st.caption(
            "Insufficient training: fewer than 60 earlier "
            "matches or model fitting failure. "
            "Unseen teams: teams absent from the earlier "
            "training history, plus pricing failures."
        )

    st.info(
        "This test evaluates prediction quality, not "
        "betting profitability. Genuine historical odds "
        "are needed to measure returns or bookmaker edge."
    )


st.divider()

st.caption(
    "PRO STARLIZARD V5 · "
    "Read-only Supabase · "
    "Chronological backtesting"
)
