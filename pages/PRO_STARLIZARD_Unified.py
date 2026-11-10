
"""PRO STARLIZARD V5.2 — Halftime-first pricing and backtesting."""

import os
import math
from datetime import date

import numpy as np
import pandas as pd
import streamlit as st
from supabase import create_client

from starlizard_pricing_engine import (
    fit_ratings,
    price_fixture,
    asian_market,
    load_historical_xg,
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

LEAGUES = {
    "comp_3039": "Premier League",
    "comp_8321": "Championship",
    "comp_4643": "Bundesliga",
    "comp_0256": "Ligue 1",
    "comp_8531": "Belgian Pro League",
}

OUTCOMES = ("home", "away", "none")


def label(cid):
    return (
        f"{LEAGUES[cid]} ({cid})"
        if cid in LEAGUES
        else str(cid)
    )


st.markdown(
    """
<style>
.block-container {
    max-width: 1050px;
    padding: .8rem .6rem 2rem;
}
h1 {font-size: 1.5rem !important}
h2, h3 {font-size: 1.1rem !important}
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
def catalogue():
    rows = load_table(
        database(),
        "historical_xg",
        "match_id,competition_id,match_date,home_team,away_team",
    )

    result = {}

    for row in rows:
        cid = str(row.get("competition_id") or "").strip()
        home = str(row.get("home_team") or "").strip()
        away = str(row.get("away_team") or "").strip()

        if cid and home and away and home != away:
            result.setdefault(cid, set()).update(
                (home, away)
            )

    return {
        key: sorted(value)
        for key, value in sorted(result.items())
    }


@st.cache_data(ttl=3600)
def ratings_for(cid, cutoff, half_life, ridge):
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


@st.cache_data(
    ttl=3600,
    show_spinner="Loading historical halftime records...",
)
def halftime_data():
    xg = load_table(
        database(),
        "historical_xg",
        "match_id,match_date,competition_id,"
        "home_team,away_team,"
        "home_ht_goals,away_ht_goals,"
        "home_goals,away_goals,"
        "home_ht_xg,away_ht_xg",
    )

    events = load_table(
        database(),
        "historical_match_events",
        "match_id,stats_data,timeline_data",
    )

    matches, rejected = build_matches(xg, events)

    metadata = {
        str(row["match_id"]): row
        for row in xg
        if row.get("match_id")
    }

    timelines = {
        str(row["match_id"]): row.get("timeline_data")
        for row in events
        if row.get("match_id")
    }

    return matches, rejected, metadata, timelines


def number_int(value):
    if isinstance(value, bool):
        return None

    try:
        number = float(value)

        if (
            math.isfinite(number)
            and number >= 0
            and number.is_integer()
        ):
            return int(number)

    except (TypeError, ValueError):
        pass

    return None


def parse_goal_sequence(match, meta, timeline):
    """
    Verify timeline against HT/FT scores.
    Return home, away, none, or None for invalid.
    """

    if not isinstance(timeline, dict):
        return None

    if timeline.get("coverage") != "full":
        return None

    events = timeline.get("events")

    if not isinstance(events, list):
        return None

    if not all(
        isinstance(event, dict)
        for event in events
    ):
        return None

    home = str(meta.get("home_team") or "")
    away = str(meta.get("away_team") or "")

    if not home or not away or home == away:
        return None

    counted = {
        "first_half": [0, 0],
        "second_half": [0, 0],
    }

    second_half = []

    for event in events:
        kind = event.get("type")

        if kind not in (
            "goal",
            "penalty_scored",
            "own_goal",
        ):
            continue

        period = event.get("period")

        if period not in counted:
            return None

        team = event.get("team")

        team_name = (
            team.get("name")
            if isinstance(team, dict)
            else None
        )

        if team_name not in (home, away):
            return None

        scorer = 0 if team_name == home else 1

        if kind == "own_goal":
            scorer = 1 - scorer

        minute = number_int(event.get("minute"))

        extra = number_int(
            event.get("extra_time")
            if event.get("extra_time") is not None
            else 0
        )

        if minute is None or extra is None:
            return None

        counted[period][scorer] += 1

        if period == "second_half":
            second_half.append(
                (minute, extra, scorer)
            )

    if counted["first_half"] != [
        match.ht_home,
        match.ht_away,
    ]:
        return None

    expected_second_half = [
        match.ft_home - match.ht_home,
        match.ft_away - match.ht_away,
    ]

    if counted["second_half"] != expected_second_half:
        return None

    if not second_half:
        return "none"

    second_half.sort(
        key=lambda item: (item[0], item[1])
    )

    first = second_half[0]

    # Different scorers with identical timestamps
    # cannot be ordered reliably.
    if any(
        item[:2] == first[:2]
        and item[2] != first[2]
        for item in second_half[1:]
    ):
        return None

    return "home" if first[2] == 0 else "away"


def next_goal_rates(sample, metadata, timelines):
    counts = {
        "home": 0,
        "away": 0,
        "none": 0,
    }

    invalid = 0

    for match in sample:
        outcome = parse_goal_sequence(
            match,
            metadata.get(str(match.match_id), {}),
            timelines.get(str(match.match_id)),
        )

        if outcome is None:
            invalid += 1
        else:
            counts[outcome] += 1

    return counts, invalid


def market_rows(sample):
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
                (
                    f"Over {line:.1f} corners 2H",
                    market_over(
                        "corners", "second_half", line
                    ),
                )
                for line in (3.5, 4.5, 5.5)
            ]
            + [
                (
                    f"Over {line:.1f} corners FT",
                    market_over("corners", "all", line),
                )
                for line in (8.5, 9.5)
            ],
        ),
        (
            "🟨 Yellow cards",
            [
                (
                    f"Over {line:.1f} yellows 2H",
                    market_over(
                        "yellows", "second_half", line
                    ),
                )
                for line in (1.5, 2.5, 3.5)
            ]
            + [
                (
                    f"Over {line:.1f} yellows FT",
                    market_over("yellows", "all", line),
                )
                for line in (3.5, 4.5)
            ],
        ),
    ]

    for heading, markets in groups:
        st.markdown(f"**{heading}**")

        rows = []

        for name, predicate in markets:
            result = price_market(sample, predicate)

            rows.append({
                "Market": name + (
                    " ⚠️"
                    if result
                    and not result["sufficient_sample"]
                    else ""
                ),
                "Probability": (
                    f"{result['probability']:.1%}"
                    if result else "—"
                ),
                "Fair odds": (
                    f"{result['fair_odds']:.2f}"
                    if result else "—"
                ),
                "N": result["sample"] if result else 0,
            })

        st.dataframe(
            pd.DataFrame(rows),
            hide_index=True,
            use_container_width=True,
        )


# =====================================================
# HALFTIME BACKTEST ENGINE
# =====================================================

@st.cache_data(ttl=3600, show_spinner=False)
def verified_goal_history(matches, metadata, timelines):
    rows = []

    for match in matches:
        match_id = str(match.match_id)
        meta = metadata.get(match_id, {})

        outcome = parse_goal_sequence(
            match,
            meta,
            timelines.get(match_id),
        )

        if outcome not in OUTCOMES:
            continue

        match_date = pd.to_datetime(
            meta.get("match_date"),
            errors="coerce",
            utc=True,
        )

        if pd.isna(match_date):
            continue

        try:
            hx = float(match.ht_xg_home)
            ax = float(match.ht_xg_away)
        except (TypeError, ValueError):
            continue

        if not (
            math.isfinite(hx)
            and math.isfinite(ax)
            and hx >= 0
            and ax >= 0
        ):
            continue

        rows.append({
            "date": match_date,
            "match_id": match_id,
            "hh": int(match.ht_home),
            "ah": int(match.ht_away),
            "hx": hx,
            "ax": ax,
            "outcome": outcome,
        })

    return pd.DataFrame(rows)


def smoothed_probabilities(rows):
    counts = rows["outcome"].value_counts()
    n = len(rows)

    return {
        outcome: (
            int(counts.get(outcome, 0)) + 1
        ) / (n + 3)
        for outcome in OUTCOMES
    }


def score_prediction(probabilities, actual):
    brier = sum(
        (
            probabilities[outcome]
            - float(outcome == actual)
        ) ** 2
        for outcome in OUTCOMES
    )

    log_loss = -math.log(
        max(probabilities[actual], 1e-12)
    )

    return brier, log_loss


def run_halftime_backtest(history, limit, tolerance):
    if history.empty or len(history) < 200:
        return pd.DataFrame(), 0

    history = history.sort_values(
        ["date", "match_id"]
    ).reset_index(drop=True)

    split = int(len(history) * 0.80)

    # Last 20% is the evaluation period.
    testing = history.iloc[split:].tail(limit)

    predictions = []

    for target in testing.itertuples(index=False):
        # Strictly earlier dates only.
        # Matches played on the same date are excluded.
        previous = history[
            (history["date"] < target.date)
            & (history["hh"] == target.hh)
            & (history["ah"] == target.ah)
        ]

        if len(previous) < 100:
            continue

        similar = previous[
            (
                previous["hx"] - target.hx
            ).abs() <= tolerance
        ]

        similar = similar[
            (
                similar["ax"] - target.ax
            ).abs() <= tolerance
        ]

        if len(similar) < 30:
            continue

        baseline = smoothed_probabilities(previous)
        model = smoothed_probabilities(similar)

        base_brier, base_log = score_prediction(
            baseline, target.outcome
        )

        model_brier, model_log = score_prediction(
            model, target.outcome
        )

        trailing = (
            "home" if target.hh < target.ah
            else "away" if target.ah < target.hh
            else None
        )

        trailing_xg = (
            target.hx if trailing == "home"
            else target.ax if trailing == "away"
            else None
        )

        flagged = (
            trailing is not None
            and trailing_xg >= 0.20
        )

        predictions.append({
            "Date": target.date.date().isoformat(),
            "Match ID": target.match_id,
            "HT score": f"{target.hh}-{target.ah}",
            "Actual": target.outcome,
            "Baseline Brier": base_brier,
            "STARLIZARD Brier": model_brier,
            "Baseline log loss": base_log,
            "STARLIZARD log loss": model_log,
            "Trailing xG flag": flagged,
            "Trailing scored next": (
                target.outcome == trailing
                if trailing is not None
                else None
            ),
            "Baseline N": len(previous),
            "STARLIZARD N": len(similar),
            "Baseline home": baseline["home"],
            "Baseline away": baseline["away"],
            "Baseline none": baseline["none"],
            "Model home": model["home"],
            "Model away": model["away"],
            "Model none": model["none"],
        })

    return pd.DataFrame(predictions), len(testing)


def display_halftime_backtest():
    st.divider()
    st.subheader("🧪 Halftime next-goal backtest")

    st.caption(
        "Chronological out-of-sample testing. "
        "Baseline: halftime score alone. "
        "STARLIZARD: halftime score plus xG. "
        "Lower Brier and log loss are better."
    )

    limit = st.selectbox(
        "Maximum recent matches to test",
        [200, 500, 1000],
        index=1,
        key="ht_test_limit",
    )

    tolerance = st.selectbox(
        "HT xG comparison tolerance",
        [0.20, 0.30, 0.40, 0.50],
        index=1,
        key="ht_test_tolerance",
    )

    if st.button(
        "Run halftime backtest",
        type="primary",
        key="run_ht_test",
    ):
        with st.spinner(
            "Verifying timelines and testing predictions..."
        ):
            history = verified_goal_history(
                matches, metadata, timelines
            )

            predictions, considered = (
                run_halftime_backtest(
                    history,
                    limit,
                    tolerance,
                )
            )

            st.session_state["ht_backtest_result"] = {
                "predictions": predictions,
                "verified": len(history),
                "considered": considered,
                "tolerance": tolerance,
            }

    result = st.session_state.get(
        "ht_backtest_result"
    )

    if result is None:
        return

    frame = result["predictions"]

    st.caption(
        f"{result['verified']:,} verified historical "
        f"sequences with usable HT xG. "
        f"{result['considered']:,} held-out matches considered."
    )

    if frame.empty:
        st.warning(
            "Not enough comparable earlier matches "
            "met the minimum sample requirements. "
            "No accuracy conclusion can be drawn."
        )
        return

    st.success(
        f"{len(frame):,} out-of-sample predictions"
    )

    base_brier = frame["Baseline Brier"].mean()
    model_brier = frame["STARLIZARD Brier"].mean()

    base_log = frame["Baseline log loss"].mean()
    model_log = frame["STARLIZARD log loss"].mean()

    st.markdown("**Overall accuracy**")

    st.dataframe(
        pd.DataFrame([
            {
                "Method": "HT score baseline",
                "Brier": round(base_brier, 4),
                "Log loss": round(base_log, 4),
            },
            {
                "Method": "STARLIZARD HT xG",
                "Brier": round(model_brier, 4),
                "Log loss": round(model_log, 4),
            },
        ]),
        hide_index=True,
        use_container_width=True,
    )

    improvement = (
        (base_brier - model_brier)
        / base_brier * 100
        if base_brier > 0 else 0
    )

    st.metric(
        "Brier improvement vs baseline",
        f"{improvement:+.2f}%",
    )

    if model_brier < base_brier:
        st.success(
            "The xG-based approach scored better "
            "than the score-only baseline on "
            "these evaluated matches."
        )
    else:
        st.warning(
            "The xG-based approach did not beat "
            "the score-only baseline on "
            "these evaluated matches."
        )

    st.markdown("**Trailing team xG ≥ 0.20**")

    flagged = frame[
        frame["Trailing xG flag"] == True
    ]

    if not flagged.empty:
        hit_rate = (
            flagged["Trailing scored next"]
            .astype(float)
            .mean()
        )

        st.write(
            f"Flagged test matches: {len(flagged)}"
        )

        st.write(
            f"Trailing team scored next: {hit_rate:.1%}"
        )

        st.write(
            "Baseline Brier: "
            f"{flagged['Baseline Brier'].mean():.4f}"
        )

        st.write(
            "STARLIZARD Brier: "
            f"{flagged['STARLIZARD Brier'].mean():.4f}"
        )
    else:
        st.info(
            "No flagged matches met the "
            "backtest sample requirements."
        )

    st.download_button(
        "Download halftime backtest results",
        frame.to_csv(index=False),
        file_name="starlizard_halftime_backtest.csv",
        mime="text/csv",
        key="download_ht_backtest",
    )

    st.caption(
        "This is an accuracy comparison, not "
        "a betting profitability test. "
        "The 0.20 xG flag is analysed as a "
        "subgroup rather than as a separately "
        "trained model. Matches without sufficient "
        "historical comparables are excluded."
    )


# =====================================================
# EXISTING PRE-MATCH BACKTEST ENGINE
# =====================================================

@st.cache_data(ttl=3600)
def test_data():
    rows = load_table(
        database(),
        "historical_xg",
        "match_id,competition_id,match_date,"
        "home_team,away_team,home_xg,away_xg,"
        "home_goals,away_goals",
    )

    data = pd.DataFrame(rows)
    original = len(data)

    if data.empty:
        return data, original

    columns = [
        "match_id",
        "competition_id",
        "match_date",
        "home_team",
        "away_team",
        "home_xg",
        "away_xg",
        "home_goals",
        "away_goals",
    ]

    data = data.dropna(subset=columns).copy()

    data["match_date"] = pd.to_datetime(
        data["match_date"],
        errors="coerce",
        utc=True,
    )

    for col in (
        "home_xg",
        "away_xg",
        "home_goals",
        "away_goals",
    ):
        data[col] = pd.to_numeric(
            data[col],
            errors="coerce",
        )

    data = data.dropna(subset=columns)

    for col in (
        "home_team",
        "away_team",
        "competition_id",
    ):
        data[col] = data[col].astype(str).str.strip()

    data = data[
        (data.home_team != "")
        & (data.away_team != "")
        & (data.home_team != data.away_team)
        & (data.competition_id != "")
    ]

    for col in (
        "home_xg",
        "away_xg",
        "home_goals",
        "away_goals",
    ):
        data = data[
            np.isfinite(data[col])
            & (data[col] >= 0)
        ]

    for col in ("home_goals", "away_goals"):
        data = data[data[col] % 1 == 0]

    data = (
        data.drop_duplicates("match_id")
        .sort_values([
            "competition_id",
            "match_date",
            "match_id",
        ])
        .reset_index(drop=True)
    )

    return data, original


def brier(probabilities, outcomes):
    return float(
        np.mean(
            (
                np.asarray(probabilities)
                - np.asarray(outcomes)
            ) ** 2
        )
    )


def summary(frame):
    def multi(prefix):
        probabilities = frame[
            [
                f"{prefix}_home",
                f"{prefix}_draw",
                f"{prefix}_away",
            ]
        ].to_numpy(float)

        outcomes = frame.outcome.to_numpy(int)
        actual = np.eye(3)[outcomes]

        brier_score = float(
            np.mean(
                np.sum(
                    (probabilities - actual) ** 2,
                    axis=1,
                )
            )
        )

        log_loss = float(
            np.mean(
                -np.log(
                    np.clip(
                        probabilities[
                            np.arange(len(probabilities)),
                            outcomes,
                        ],
                        1e-12,
                        1,
                    )
                )
            )
        )

        return brier_score, log_loss

    model_brier, model_log = multi("model")
    base_brier, base_log = multi("base")

    return {
        "Matches": len(frame),
        "1X2 Brier": round(model_brier, 4),
        "Baseline Brier": round(base_brier, 4),
        "1X2 log loss": round(model_log, 4),
        "Baseline log loss": round(base_log, 4),
        "Over 2.5 Brier": round(
            brier(
                frame.model_over,
                frame.actual_over,
            ),
            4,
        ),
        "Baseline Over 2.5": round(
            brier(
                frame.base_over,
                frame.actual_over,
            ),
            4,
        ),
        "BTTS Brier": round(
            brier(
                frame.model_btts,
                frame.actual_btts,
            ),
            4,
        ),
        "Baseline BTTS": round(
            brier(
                frame.base_btts,
                frame.actual_btts,
            ),
            4,
        ),
    }


def run_test(data, months):
    today = pd.Timestamp.now(
        tz="UTC"
    ).tz_localize(None).to_period("M")

    last = today - 1

    predictions = []
    audit = []

    competitions = sorted(
        data.competition_id.unique()
    )

    bar = st.progress(0)

    for index, cid in enumerate(competitions):
        league = data[
            data.competition_id == cid
        ]

        attempted = 0
        insufficient = 0
        skipped = 0

        for step in range(months):
            month = last - (
                months - 1 - step
            )

            cutoff = pd.Timestamp(
                month.start_time
            ).tz_localize("UTC")

            end = pd.Timestamp(
                (month + 1).start_time
            ).tz_localize("UTC")

            train = league[
                league.match_date < cutoff
            ]

            test = league[
                (league.match_date >= cutoff)
                & (league.match_date < end)
            ]

            if test.empty:
                continue

            attempted += len(test)

            if len(train) < 60:
                insufficient += len(test)
                continue

            before = cutoff.strftime(
                "%Y-%m-%d"
            )

            try:
                ratings = fit_ratings(
                    train[
                        [
                            "match_id",
                            "competition_id",
                            "match_date",
                            "home_team",
                            "away_team",
                            "home_xg",
                            "away_xg",
                        ]
                    ],
                    cid,
                    before,
                    half_life_days=180,
                    ridge=10,
                    minimum_matches=60,
                )
            except (
                ValueError,
                np.linalg.LinAlgError,
            ):
                insufficient += len(test)
                continue

            n = len(train)

            base = [
                (
                    (
                        train.home_goals
                        > train.away_goals
                    ).sum() + 1
                ) / (n + 3),
                (
                    (
                        train.home_goals
                        == train.away_goals
                    ).sum() + 1
                ) / (n + 3),
                (
                    (
                        train.home_goals
                        < train.away_goals
                    ).sum() + 1
                ) / (n + 3),
            ]

            base_over = (
                (
                    train.home_goals
                    + train.away_goals >= 3
                ).sum() + 1
            ) / (n + 2)

            base_btts = (
                (
                    (train.home_goals > 0)
                    & (train.away_goals > 0)
                ).sum() + 1
            ) / (n + 2)

            for row in test.itertuples(index=False):
                if (
                    row.home_team not in ratings.teams
                    or row.away_team not in ratings.teams
                ):
                    skipped += 1
                    continue

                try:
                    probabilities = price_fixture(
                        ratings,
                        row.home_team,
                        row.away_team,
                    )["probabilities"]
                except (
                    ValueError,
                    OverflowError,
                ):
                    skipped += 1
                    continue

                outcome = (
                    0 if row.home_goals > row.away_goals
                    else 1 if row.home_goals == row.away_goals
                    else 2
                )

                predictions.append({
                    "League": label(cid),
                    "match_id": row.match_id,
                    "month": str(month),
                    "outcome": outcome,
                    "model_home": probabilities["home"],
                    "model_draw": probabilities["draw"],
                    "model_away": probabilities["away"],
                    "base_home": base[0],
                    "base_draw": base[1],
                    "base_away": base[2],
                    "model_over": probabilities["over_2_5"],
                    "base_over": base_over,
                    "actual_over": int(
                        row.home_goals
                        + row.away_goals >= 3
                    ),
                    "model_btts": probabilities["btts_yes"],
                    "base_btts": base_btts,
                    "actual_btts": int(
                        row.home_goals > 0
                        and row.away_goals > 0
                    ),
                })

        audit.append({
            "League": label(cid),
            "Test window matches": attempted,
            "Insufficient training": insufficient,
            "Unseen/pricing failures": skipped,
        })

        bar.progress(
            (index + 1) / len(competitions)
        )

    bar.empty()

    return (
        pd.DataFrame(predictions),
        pd.DataFrame(audit),
    )


# =====================================================
# MAIN DASHBOARD
# =====================================================

st.title("🦎 PRO STARLIZARD")
st.caption(
    "Halftime-first unified pricing | V5.2"
)

tab_ht, tab_pre, tab_test = st.tabs([
    "⏱️ Halftime",
    "⚽ Pre-match",
    "📊 Backtest",
])


# =====================================================
# HALFTIME TAB
# =====================================================

with tab_ht:
    st.subheader(
        "Halftime pricing — main dashboard"
    )

    try:
        (
            matches,
            rejected,
            metadata,
            timelines,
        ) = halftime_data()

    except Exception as exc:
        st.error(
            f"Historical data failed: {exc}"
        )
        matches = []

    if matches:
        st.caption(
            f"{len(matches):,} score-valid "
            "historical matches loaded"
        )

        c1, c2 = st.columns(2)

        with c1:
            home_name = st.text_input(
                "Home team label",
                "Home",
                key="ht_home_name",
            )

        with c2:
            away_name = st.text_input(
                "Away team label",
                "Away",
                key="ht_away_name",
            )

        c1, c2 = st.columns(2)

        with c1:
            hh = st.number_input(
                f"{home_name} HT goals",
                0, 10, 0,
                key="ht_home_goals",
            )

            hx = st.number_input(
                f"{home_name} HT xG",
                0.0, 10.0, 0.85, 0.05,
                key="ht_home_xg",
            )

        with c2:
            ah = st.number_input(
                f"{away_name} HT goals",
                0, 10, 1,
                key="ht_away_goals",
            )

            ax = st.number_input(
                f"{away_name} HT xG",
                0.0, 10.0, 0.35, 0.05,
                key="ht_away_xg",
            )

        with st.expander("Historical filters"):
            tolerance = st.slider(
                "HT xG tolerance",
                0.10, 1.00, 0.30, 0.05,
                key="ht_tolerance",
            )

            league_filter = st.selectbox(
                "League scope",
                ["All leagues"]
                + sorted({
                    match.competition_id
                    for match in matches
                }),
                format_func=lambda value: (
                    value
                    if value == "All leagues"
                    else label(value)
                ),
            )

        sample = comparable_matches(
            matches,
            int(hh),
            int(ah),
            float(hx),
            float(ax),
            tolerance=float(tolerance),
            before_date=date.today().isoformat(),
            competition_id=(
                None
                if league_filter == "All leagues"
                else league_filter
            ),
        )

        st.markdown(
            f"**{home_name} {hh}–{ah} "
            f"{away_name}** · "
            f"{len(sample)} comparable matches"
        )

        if len(sample) < 100:
            st.warning(
                "Small historical sample. "
                "Prices may be unstable."
            )

        st.subheader(
            "🥅 First goal after halftime"
        )

        counts, invalid = next_goal_rates(
            sample,
            metadata,
            timelines,
        )

        n = sum(counts.values())

        if n:
            rows = []

            for outcome, display in [
                (
                    "home",
                    f"{home_name} scores next",
                ),
                (
                    "away",
                    f"{away_name} scores next",
                ),
                (
                    "none",
                    "No second-half goal",
                ),
            ]:
                probability = counts[outcome] / n

                rows.append({
                    "Outcome": display,
                    "Probability": f"{probability:.1%}",
                    "Fair odds": (
                        f"{1 / probability:.2f}"
                        if probability else "—"
                    ),
                    "Count": counts[outcome],
                })

            st.dataframe(
                pd.DataFrame(rows),
                hide_index=True,
                use_container_width=True,
            )

            st.caption(
                f"{n} verified goal sequences; "
                f"{invalid} excluded for missing, "
                "inconsistent or ambiguous timelines. "
                "Three outcomes total 100%."
            )

            if n < 100:
                st.warning(
                    "Next-goal sample below "
                    "100 verified sequences."
                )

            if hh != ah:
                trailing = (
                    "home" if hh < ah else "away"
                )

                trailing_xg = (
                    hx if trailing == "home" else ax
                )

                if trailing_xg >= 0.20:
                    probability = (
                        counts[trailing] / n
                    )

                    st.info(
                        "Automatic flag: trailing team "
                        f"has HT xG {trailing_xg:.2f} "
                        "(≥ 0.20). "
                        "In this comparable sample, "
                        "the trailing team scored the "
                        "first second-half goal "
                        f"{counts[trailing]}/{n} "
                        f"times ({probability:.1%}). "
                        "Historical frequency, "
                        "not a proven betting edge."
                    )
        else:
            st.warning(
                "No verified goal sequences "
                "in this sample."
            )

        st.subheader(
            "Second-half goals, corners and cards"
        )

        if sample:
            market_rows(sample)

        st.caption(
            "Historical conditional frequencies, "
            "not calibrated team-specific forecasts. "
            "No real-time odds are fetched."
        )

        # The new V5.2 halftime backtest
        display_halftime_backtest()


# =====================================================
# PRE-MATCH TAB
# =====================================================

with tab_pre:
    st.subheader(
        "Pre-match pricing"
    )

    try:
        leagues = catalogue()
    except Exception as exc:
        st.error(
            f"Catalogue failed: {exc}"
        )
        leagues = {}

    if leagues:
        cid = st.selectbox(
            "League",
            list(leagues),
            format_func=label,
            key="pre_comp",
        )

        teams = leagues[cid]

        if len(teams) >= 2:
            c1, c2 = st.columns(2)

            with c1:
                home = st.selectbox(
                    "Home team",
                    teams,
                    key="pre_home",
                )

            with c2:
                away = st.selectbox(
                    "Away team",
                    teams,
                    index=1,
                    key="pre_away",
                )

            cutoff = st.date_input(
                "Price fixture using data before",
                date.today(),
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
                st.warning(
                    "Choose two different teams."
                )
            else:
                try:
                    rating = ratings_for(
                        cid,
                        cutoff.isoformat(),
                        half_life,
                        ridge,
                    )

                    priced = price_fixture(
                        rating, home, away
                    )

                except Exception as exc:
                    st.warning(
                        f"Could not price fixture: {exc}"
                    )
                    priced = None

                if priced:
                    st.markdown(
                        f"**{home} v {away}**"
                    )

                    c1, c2 = st.columns(2)

                    c1.metric(
                        "Home xG",
                        f"{priced['home_xg']:.2f}",
                    )

                    c2.metric(
                        "Away xG",
                        f"{priced['away_xg']:.2f}",
                    )

                    st.caption(
                        f"{rating.matches} training "
                        "matches across "
                        f"{len(rating.teams)} teams"
                    )

                    keys = [
                        ("Home win", "home"),
                        ("Draw", "draw"),
                        ("Away win", "away"),
                        ("Over 2.5", "over_2_5"),
                        ("Under 2.5", "under_2_5"),
                        ("BTTS Yes", "btts_yes"),
                        ("BTTS No", "btts_no"),
                    ]

                    st.dataframe(
                        pd.DataFrame([
                            {
                                "Market": name,
                                "Probability": (
                                    f"{priced['probabilities'][key]:.1%}"
                                ),
                                "Fair odds": (
                                    f"{priced['fair_odds'][key]:.2f}"
                                ),
                            }
                            for name, key in keys
                        ]),
                        hide_index=True,
                        use_container_width=True,
                    )

                    st.subheader("Asian pricing")

                    choices = {
                        "Home handicap": "home_handicap",
                        "Away handicap": "away_handicap",
                        "Over goals": "over_goals",
                        "Under goals": "under_goals",
                    }

                    choice = st.selectbox(
                        "Asian market",
                        list(choices),
                        key="asian_market",
                    )

                    handicap = (
                        "handicap" in choice
                    )

                    lines = (
                        [
                            i / 4
                            for i in range(-12, 13)
                        ]
                        if handicap
                        else [
                            i / 4
                            for i in range(2, 25)
                        ]
                    )

                    line = st.selectbox(
                        "Asian line",
                        lines,
                        index=lines.index(
                            0.0 if handicap else 2.5
                        ),
                        key="asian_line",
                    )

                    asian = asian_market(
                        priced["matrix"],
                        choices[choice],
                        line,
                    )

                    if asian["fair_odds"] is None:
                        st.warning(
                            "No finite fair odds "
                            "for this line."
                        )
                    else:
                        st.metric(
                            "Asian fair odds",
                            f"{asian['fair_odds']:.3f}",
                        )

                        quote = st.number_input(
                            "Bookmaker decimal odds",
                            min_value=1.01,
                            max_value=100.0,
                            value=1.95,
                            step=0.01,
                            key="asian_quote",
                        )

                        roi = (
                            asian["win_units"]
                            * (quote - 1)
                            - asian["loss_units"]
                        )

                        st.metric(
                            "Model-implied ROI",
                            f"{roi:+.2%}",
                        )

                    with st.expander(
                        "Correct-score prices"
                    ):
                        st.dataframe(
                            pd.DataFrame([
                                {
                                    "Score": score,
                                    "Probability": f"{p:.2%}",
                                    "Fair odds": f"{1 / p:.2f}",
                                }
                                for score, p in
                                priced["correct_scores"].items()
                                if p > 0
                            ]),
                            hide_index=True,
                            use_container_width=True,
                        )

                    st.caption(
                        "Experimental prices. "
                        "Model-implied ROI is not "
                        "proven betting profit."
                    )
        else:
            st.warning(
                "Not enough teams in this league."
            )


# =====================================================
# PRE-MATCH BACKTEST TAB
# =====================================================

with tab_test:
    st.subheader(
        "Pre-match historical accuracy backtest"
    )

    st.caption(
        "Existing pre-match model. "
        "Expanding training history and "
        "complete calendar months only. "
        "Lower scores are better."
    )

    months = st.selectbox(
        "Recent complete months",
        [3, 6, 9, 12],
        index=1,
        key="test_periods",
    )

    if st.button(
        "Run historical accuracy test",
        type="primary",
        key="run_backtest",
    ):
        try:
            history, loaded = test_data()

            predictions, audit = (
                run_test(history, months)
                if not history.empty
                else (
                    pd.DataFrame(),
                    pd.DataFrame(),
                )
            )

            st.session_state["test_result"] = (
                predictions,
                audit,
                len(history),
                loaded,
                months,
            )

        except Exception as exc:
            st.error(
                f"Backtest failed: {exc}"
            )

    if "test_result" in st.session_state:
        (
            predictions,
            audit,
            valid,
            loaded,
            months_done,
        ) = st.session_state["test_result"]

        st.caption(
            f"{loaded:,} database rows; "
            f"{valid:,} valid xG and "
            "final-score records; "
            f"{months_done} months selected"
        )

        if predictions.empty:
            st.warning(
                "No out-of-sample predictions "
                "in this test window."
            )
        else:
            st.success(
                f"{len(predictions):,} "
                "out-of-sample predictions"
            )

            st.subheader("Overall accuracy")

            st.dataframe(
                pd.DataFrame([
                    summary(predictions)
                ]),
                hide_index=True,
                use_container_width=True,
            )

            st.subheader("By league")

            league_rows = []

            for league, part in predictions.groupby(
                "League"
            ):
                item = summary(part)
                item["League"] = league
                league_rows.append(item)

            st.dataframe(
                pd.DataFrame(
                    league_rows
                ).sort_values(
                    "Matches",
                    ascending=False,
                ),
                hide_index=True,
                use_container_width=True,
            )

            st.subheader(
                "Probability calibration"
            )

            market = st.selectbox(
                "Calibration market",
                [
                    "Over 2.5 goals",
                    "BTTS Yes",
                ],
                key="calibration_market",
            )

            if market == "Over 2.5 goals":
                pcol = "model_over"
                ycol = "actual_over"
            else:
                pcol = "model_btts"
                ycol = "actual_btts"

            bins = []

            for index in range(10):
                low = index / 10
                high = (index + 1) / 10

                part = predictions[
                    (predictions[pcol] >= low)
                    & (
                        (
                            predictions[pcol] < high
                        )
                        if index < 9
                        else (
                            predictions[pcol] <= high
                        )
                    )
                ]

                if len(part):
                    bins.append({
                        "Band": (
                            f"{low:.0%}–{high:.0%}"
                        ),
                        "N": len(part),
                        "Predicted": round(
                            float(
                                part[pcol].mean()
                            ),
                            3,
                        ),
                        "Actual": round(
                            float(
                                part[ycol].mean()
                            ),
                            3,
                        ),
                    })

            st.dataframe(
                pd.DataFrame(bins),
                hide_index=True,
                use_container_width=True,
            )

            st.download_button(
                "Download backtest predictions",
                predictions.to_csv(index=False),
                file_name=(
                    "starlizard_backtest_predictions.csv"
                ),
                mime="text/csv",
            )

        st.subheader(
            "Coverage and exclusions"
        )

        st.dataframe(
            audit,
            hide_index=True,
            use_container_width=True,
        )

    st.info(
        "Prediction accuracy is not "
        "betting profitability. "
        "Genuine historical bookmaker odds "
        "are needed for returns testing."
    )


st.divider()

st.caption(
    "PRO STARLIZARD V5.2 · "
    "Read-only Supabase · Halftime-first"
)
