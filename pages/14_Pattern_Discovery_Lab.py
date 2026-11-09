
import streamlit as st
import pandas as pd
import numpy as np
from supabase import create_client

st.set_page_config(
    page_title="PRO STARLIZARD | Pattern Discovery V2",
    page_icon="🔎",
    layout="wide",
)

st.title("🔎 PRO STARLIZARD")
st.subheader("Pattern Discovery Lab V2")
st.caption(
    "Automatic historical pattern discovery | "
    "Goals and verified next-goal timelines"
)


# -----------------------------------------
# DATABASE
# -----------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def load_table(table_name, columns):
    db = create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_SECRET_KEY"],
    )

    records = []
    last_id = None

    while True:
        query = (
            db.table(table_name)
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


def load_goals():
    return load_table(
        "historical_xg",
        "match_id,match_date,home_ht_goals,"
        "away_ht_goals,home_goals,away_goals,"
        "home_ht_xg,away_ht_xg",
    )


def load_next_goal():
    return load_table(
        "starlizard_verified_next_goal",
        "match_id,match_date,home_ht_goals,"
        "away_ht_goals,home_ht_xg,away_ht_xg,"
        "trailing_team_scored_first",
    )


# -----------------------------------------
# DATA PREPARATION
# -----------------------------------------

def prepare(df, market):
    df = df.copy()

    numeric = [
        "home_ht_goals",
        "away_ht_goals",
        "home_ht_xg",
        "away_ht_xg",
    ]

    if market == "second_half":
        numeric += ["home_goals", "away_goals"]

    for column in numeric:
        df[column] = pd.to_numeric(
            df[column], errors="coerce"
        )

    df["match_date"] = pd.to_datetime(
        df["match_date"], errors="coerce"
    )

    df = df.dropna(
        subset=numeric + ["match_date", "match_id"]
    )

    valid = (
        (df["home_ht_goals"] >= 0)
        & (df["away_ht_goals"] >= 0)
        & (df["home_ht_xg"] >= 0)
        & (df["away_ht_xg"] >= 0)
        & (
            df["home_ht_goals"]
            != df["away_ht_goals"]
        )
    )

    if market == "second_half":
        valid &= (
            (df["home_goals"] >= df["home_ht_goals"])
            & (df["away_goals"] >= df["away_ht_goals"])
        )

    df = df.loc[valid].copy()
    df = df.drop_duplicates(subset=["match_id"])

    home_trailing = (
        df["home_ht_goals"] < df["away_ht_goals"]
    )

    df["trailing_side"] = np.where(
        home_trailing, "Home", "Away"
    )

    df["deficit"] = (
        df["home_ht_goals"] - df["away_ht_goals"]
    ).abs().astype(int)

    df["trailing_xg"] = np.where(
        home_trailing,
        df["home_ht_xg"],
        df["away_ht_xg"],
    )

    df["leading_xg"] = np.where(
        home_trailing,
        df["away_ht_xg"],
        df["home_ht_xg"],
    )

    df["xg_difference"] = (
        df["trailing_xg"] - df["leading_xg"]
    )

    df["xg_band"] = pd.cut(
        df["trailing_xg"],
        bins=[-0.001, 0.20, 0.40, 0.80, 1.20, np.inf],
        labels=[
            "Under 0.20",
            "0.20–0.39",
            "0.40–0.79",
            "0.80–1.19",
            "1.20+",
        ],
        right=False,
    )

    df["dominance"] = pd.cut(
        df["xg_difference"],
        bins=[-np.inf, -0.50, 0, 0.50, np.inf],
        labels=[
            "Outplayed by 0.50+ xG",
            "Behind on xG",
            "Ahead by under 0.50 xG",
            "Ahead by 0.50+ xG",
        ],
        right=False,
    )

    if market == "second_half":
        goals = np.where(
            home_trailing,
            df["home_goals"] - df["home_ht_goals"],
            df["away_goals"] - df["away_ht_goals"],
        )

        df["hit"] = (goals > 0).astype(int)

    else:
        # Verified NULL outcomes have been checked:
        # they are genuine goalless second halves.
        # These must count as LOSSES, not disappear.
        values = (
            df["trailing_team_scored_first"]
            .astype("string")
            .str.lower()
        )

        df["hit"] = (
            (values == "true")
            .fillna(False)
            .astype(int)
        )

    return df.sort_values(
        ["match_date", "match_id"]
    ).reset_index(drop=True)


# -----------------------------------------
# STATISTICS
# -----------------------------------------

def wilson_interval(hits, n):
    if n == 0:
        return (0.0, 1.0)

    z = 1.96
    p = hits / n
    denom = 1 + z**2 / n
    centre = p + z**2 / (2 * n)

    margin = z * np.sqrt(
        p * (1 - p) / n
        + z**2 / (4 * n**2)
    )

    return (
        max(0, (centre - margin) / denom),
        min(1, (centre + margin) / denom),
    )


def chronological_split(df):
    # Keep matches on the same date together.
    dates = sorted(df["match_date"].unique())

    if len(dates) < 2:
        return df.iloc[:0], df.iloc[:0], None

    index = min(
        len(dates) - 1,
        max(1, int(len(dates) * 0.70)),
    )

    cutoff = dates[index]

    train = df[df["match_date"] < cutoff].copy()
    test = df[df["match_date"] >= cutoff].copy()

    return train, test, cutoff


def discover(train, test, minimum):
    dimensions = [
        ["trailing_side"],
        ["trailing_side", "deficit"],
        ["trailing_side", "xg_band"],
        ["trailing_side", "dominance"],
        ["trailing_side", "deficit", "xg_band"],
        ["trailing_side", "deficit", "dominance"],
    ]

    baseline = train["hit"].mean()
    results = []

    for fields in dimensions:
        grouped = train.groupby(
            fields, observed=True
        )

        for keys, group in grouped:
            if not isinstance(keys, tuple):
                keys = (keys,)

            n = len(group)

            if n < minimum:
                continue

            mask = pd.Series(True, index=test.index)

            for field, value in zip(fields, keys):
                mask &= test[field] == value

            holdout = test.loc[mask]
            test_n = len(holdout)

            if test_n < 30:
                continue

            hits = int(group["hit"].sum())
            test_hits = int(holdout["hit"].sum())

            rate = hits / n
            test_rate = test_hits / test_n

            lower, upper = wilson_interval(
                test_hits, test_n
            )

            side = keys[
                fields.index("trailing_side")
            ]

            side_baseline = train.loc[
                train["trailing_side"] == side,
                "hit",
            ].mean()

            description = " | ".join(
                f"{field.replace('_', ' ')}: {value}"
                for field, value in zip(fields, keys)
            )

            results.append({
                "Pattern": description,
                "Training matches": n,
                "Training hit %": round(
                    rate * 100, 2
                ),
                "Training lift vs side pp": round(
                    (rate - side_baseline) * 100, 2
                ),
                "Test matches": test_n,
                "Test hits": test_hits,
                "Test hit %": round(
                    test_rate * 100, 2
                ),
                "Test fair odds": (
                    round(1 / test_rate, 2)
                    if test_rate > 0
                    else np.nan
                ),
                "Test 95% lower %": round(
                    lower * 100, 2
                ),
                "Test 95% upper %": round(
                    upper * 100, 2
                ),
            })

    return pd.DataFrame(results), baseline


# -----------------------------------------
# INTERFACE
# -----------------------------------------

market_choice = st.radio(
    "Select research market",
    [
        "Trailing team scores in second half",
        "Trailing team scores FIRST second-half goal",
    ],
)

is_next_goal = (
    market_choice
    == "Trailing team scores FIRST second-half goal"
)

market = (
    "next_goal" if is_next_goal
    else "second_half"
)

st.divider()

try:
    with st.spinner("Loading historical data..."):
        if is_next_goal:
            raw = load_next_goal()
        else:
            raw = load_goals()

    if raw.empty:
        st.warning("No records returned.")
        st.stop()

    data = prepare(raw, market)

    st.success("Connected to Supabase successfully!")

    col1, col2 = st.columns(2)

    with col1:
        st.metric(
            "Historical records loaded",
            f"{len(raw):,}",
        )

    with col2:
        st.metric(
            "Usable trailing-team matches",
            f"{len(data):,}",
        )

    # Overall results for independent validation.
    total_matches = len(data)
    total_hits = int(data["hit"].sum())
    overall_rate = (
        total_hits / total_matches
        if total_matches else 0
    )

    st.subheader("Overall historical results")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Matches",
            f"{total_matches:,}",
        )

    with col2:
        st.metric(
            "Successful outcomes",
            f"{total_hits:,}",
        )

    with col3:
        st.metric(
            "Overall strike rate",
            f"{overall_rate * 100:.2f}%",
        )

    if is_next_goal:
        st.info(
            "Verified next-goal market: the trailing "
            "team must score the FIRST goal after "
            "half-time. Matches with no second-half "
            "goal count as losses."
        )

        st.caption(
            "Source: starlizard_verified_next_goal. "
            "NULL first-scorer outcomes count as "
            "losses after database verification."
        )

        # Cross-check against the verified
        # database audit from November 2026.
        if (
            total_matches == 7143
            and total_hits == 2745
        ):
            st.success(
                "Verified audit matched: "
                "7,143 matches, 2,745 wins, "
                "38.43% strike rate."
            )
        else:
            st.warning(
                "Current results differ from the "
                "previous verified audit. This may "
                "reflect new data or changed filters. "
                "Review before relying on results."
            )

    else:
        st.info(
            "Full-time score market: the trailing "
            "team must score at least once in the "
            "second half, regardless of which "
            "team scores first."
        )

    if len(data) < 300:
        st.warning(
            "Not enough usable matches for research."
        )
        st.stop()

    train, test, cutoff = chronological_split(data)

    if len(train) < 100 or len(test) < 30:
        st.warning(
            "Insufficient training or testing data."
        )
        st.stop()

    st.subheader("Chronological testing")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Training",
            f"{len(train):,}",
        )

    with col2:
        st.metric(
            "Later testing",
            f"{len(test):,}",
        )

    with col3:
        st.metric(
            "Training baseline",
            f"{train['hit'].mean() * 100:.2f}%",
        )

    st.caption(
        f"Test period begins: "
        f"{pd.Timestamp(cutoff).date()}. "
        "All matches on the cutoff date remain "
        "in the test set."
    )

    minimum = st.slider(
        "Minimum training matches per pattern",
        min_value=50,
        max_value=500,
        value=150,
        step=50,
    )

    results, baseline = discover(
        train, test, minimum
    )

    st.subheader("Automatically discovered patterns")

    if results.empty:
        st.warning(
            "No patterns met both the training "
            "and test sample requirements."
        )
        st.stop()

    results = results.sort_values(
        [
            "Training lift vs side pp",
            "Training matches",
        ],
        ascending=[False, False],
    ).reset_index(drop=True)

    st.caption(
        "Ranked by training-period lift versus "
        "the same home/away baseline. "
        "Test results are shown separately."
    )

    st.dataframe(
        results,
        use_container_width=True,
        hide_index=True,
    )

    csv = results.to_csv(index=False)

    st.download_button(
        "Download research results CSV",
        data=csv,
        file_name=(
            "starlizard_next_goal_patterns.csv"
            if is_next_goal
            else "starlizard_second_half_patterns.csv"
        ),
        mime="text/csv",
    )

    st.subheader("Research safeguards")

    st.write(
        "The training period is used to identify "
        "patterns. Later matches are used to "
        "evaluate them."
    )

    st.write(
        "Fair odds are calculated from observed "
        "test hit rates. Confidence intervals "
        "show uncertainty, not guaranteed "
        "future probabilities."
    )

    st.warning(
        "This is a research engine, not yet a "
        "proven value-betting scanner. Patterns "
        "overlap, multiple testing can create "
        "false discoveries, and we still need "
        "market odds, commission, calibration "
        "and independent forward validation."
    )

    st.caption(
        "Read-only database access | "
        "No TheStatsAPI calls | "
        "Collectors unaffected"
    )

except Exception as error:
    st.error(
        "Pattern Discovery Lab V2 could not load."
    )
    st.exception(error)
