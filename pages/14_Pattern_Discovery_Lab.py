
import streamlit as st
import pandas as pd
import numpy as np
from supabase import create_client

st.set_page_config(
    page_title="PRO STARLIZARD | Pattern Discovery",
    page_icon="🔎",
    layout="wide",
)

st.title("🔎 PRO STARLIZARD")
st.subheader("Pattern Discovery Lab")

st.caption(
    "Automatic historical research | "
    "Read-only Supabase access | "
    "No football API calls"
)


# -----------------------------------------
# DATABASE CONNECTION
# -----------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def load_matches():

    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_SECRET_KEY"]

    db = create_client(url, key)

    columns = (
        "match_id,match_date,"
        "home_team,away_team,"
        "home_ht_goals,away_ht_goals,"
        "home_goals,away_goals,"
        "home_ht_xg,away_ht_xg"
    )

    records = []
    last_id = None

    while True:

        query = (
            db.table("historical_xg")
            .select(columns)
            .order("match_id")
            .limit(500)
        )

        if last_id is not None:
            query = query.gt(
                "match_id", last_id
            )

        response = query.execute()
        batch = response.data or []

        if not batch:
            break

        records.extend(batch)
        last_id = batch[-1]["match_id"]

        if len(batch) < 500:
            break

    return pd.DataFrame(records)


# -----------------------------------------
# STATISTICAL FUNCTIONS
# -----------------------------------------

def wilson_lower(hits, total):

    if total <= 0:
        return 0.0

    z = 1.96
    p = hits / total

    denominator = 1 + z**2 / total

    centre = p + z**2 / (2 * total)

    margin = z * np.sqrt(
        p * (1 - p) / total
        + z**2 / (4 * total**2)
    )

    return max(
        0.0,
        (centre - margin) / denominator
    )


def prepare_data(df):

    df = df.copy()

    numeric_columns = [
        "home_ht_goals",
        "away_ht_goals",
        "home_goals",
        "away_goals",
        "home_ht_xg",
        "away_ht_xg",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    df["match_date"] = pd.to_datetime(
        df["match_date"],
        errors="coerce"
    )

    df = df.dropna(
        subset=numeric_columns + ["match_date"]
    ).copy()

    df = df[
        (df["home_ht_xg"] >= 0)
        & (df["away_ht_xg"] >= 0)
        & (
            df["home_goals"]
            >= df["home_ht_goals"]
        )
        & (
            df["away_goals"]
            >= df["away_ht_goals"]
        )
        & (
            df["home_ht_goals"]
            != df["away_ht_goals"]
        )
    ].copy()

    df = df.sort_values(
        ["match_date", "match_id"]
    ).reset_index(drop=True)

    home_trailing = (
        df["home_ht_goals"]
        < df["away_ht_goals"]
    )

    df["trailing_side"] = np.where(
        home_trailing,
        "Home",
        "Away"
    )

    df["deficit"] = abs(
        df["home_ht_goals"]
        - df["away_ht_goals"]
    ).astype(int)

    df["trailing_xg"] = np.where(
        home_trailing,
        df["home_ht_xg"],
        df["away_ht_xg"]
    )

    df["leading_xg"] = np.where(
        home_trailing,
        df["away_ht_xg"],
        df["home_ht_xg"]
    )

    df["xg_difference"] = (
        df["trailing_xg"]
        - df["leading_xg"]
    )

    trailing_goals_2h = np.where(
        home_trailing,
        df["home_goals"]
        - df["home_ht_goals"],
        df["away_goals"]
        - df["away_ht_goals"]
    )

    df["scored_second_half"] = (
        trailing_goals_2h > 0
    ).astype(int)

    df["xg_band"] = pd.cut(
        df["trailing_xg"],
        bins=[
            -0.001,
            0.20,
            0.40,
            0.80,
            1.20,
            np.inf
        ],
        labels=[
            "Under 0.20",
            "0.20–0.39",
            "0.40–0.79",
            "0.80–1.19",
            "1.20+"
        ],
        right=False
    )

    df["dominance"] = pd.cut(
        df["xg_difference"],
        bins=[
            -np.inf,
            -0.50,
            0,
            0.50,
            np.inf
        ],
        labels=[
            "Outplayed by 0.50+ xG",
            "Behind on xG",
            "Ahead by under 0.50 xG",
            "Ahead by 0.50+ xG"
        ],
        right=False
    )

    return df


# -----------------------------------------
# AUTOMATIC PATTERN DISCOVERY
# -----------------------------------------

def discover_patterns(
    train,
    test,
    minimum_sample
):

    dimensions = [
        ["trailing_side", "deficit"],
        ["trailing_side", "xg_band"],
        ["trailing_side", "dominance"],
        [
            "trailing_side",
            "deficit",
            "xg_band"
        ],
        [
            "trailing_side",
            "deficit",
            "dominance"
        ],
    ]

    baseline = (
        train["scored_second_half"].mean()
    )

    results = []

    for fields in dimensions:

        groups = train.groupby(
            fields,
            observed=True
        )

        for keys, group in groups:

            if not isinstance(keys, tuple):
                keys = (keys,)

            sample_size = len(group)

            if sample_size < minimum_sample:
                continue

            mask = pd.Series(
                True,
                index=test.index
            )

            for field, value in zip(
                fields, keys
            ):
                mask &= (
                    test[field] == value
                )

            holdout = test.loc[mask]

            if len(holdout) < 30:
                continue

            training_hits = int(
                group[
                    "scored_second_half"
                ].sum()
            )

            training_rate = (
                training_hits / sample_size
            )

            test_hits = int(
                holdout[
                    "scored_second_half"
                ].sum()
            )

            test_size = len(holdout)

            test_rate = (
                test_hits / test_size
            )

            pattern_name = " | ".join(
                f"{field.replace('_', ' ')}: {value}"
                for field, value in zip(
                    fields, keys
                )
            )

            results.append({
                "Pattern": pattern_name,
                "Training matches": sample_size,
                "Training hit %": round(
                    training_rate * 100, 2
                ),
                "Test matches": test_size,
                "Test hit %": round(
                    test_rate * 100, 2
                ),
                "Test fair odds": (
                    round(1 / test_rate, 2)
                    if test_rate > 0
                    else np.nan
                ),
                "Test lower 95% %": round(
                    wilson_lower(
                        test_hits,
                        test_size
                    ) * 100,
                    2
                ),
                "Training lift pp": round(
                    (
                        training_rate - baseline
                    ) * 100,
                    2
                ),
            })

    return (
        pd.DataFrame(results),
        baseline
    )


# -----------------------------------------
# STREAMLIT INTERFACE
# -----------------------------------------

try:

    with st.spinner(
        "Loading historical database..."
    ):
        raw = load_matches()

    if raw.empty:
        st.warning(
            "No historical matches returned."
        )
        st.stop()

    data = prepare_data(raw)

    st.success(
        "Connected to Supabase successfully!"
    )

    st.metric(
        "Historical records loaded",
        f"{len(raw):,}"
    )

    st.metric(
        "Usable trailing-team matches",
        f"{len(data):,}"
    )

    st.info(
        "Version 1 investigates whether "
        "a team trailing at half-time "
        "scores at least once in the "
        "second half. This is different "
        "from the first second-half "
        "goal market."
    )

    if len(data) < 300:
        st.warning(
            "Not enough matches for analysis."
        )
        st.stop()

    split = int(
        len(data) * 0.70
    )

    train = data.iloc[
        :split
    ].copy()

    test = data.iloc[
        split:
    ].copy()

    st.subheader(
        "Historical testing"
    )

    col1, col2 = st.columns(2)

    with col1:
        st.metric(
            "Training matches",
            f"{len(train):,}"
        )

    with col2:
        st.metric(
            "Later test matches",
            f"{len(test):,}"
        )

    st.caption(
        "Matches are ordered by date. "
        "Earlier matches are used for "
        "pattern discovery, while later "
        "matches are reserved for testing."
    )

    minimum = st.slider(
        "Minimum training sample",
        min_value=50,
        max_value=500,
        value=150,
        step=50
    )

    results, baseline = discover_patterns(
        train,
        test,
        minimum
    )

    st.metric(
        "Overall training hit rate",
        f"{baseline * 100:.2f}%"
    )

    if results.empty:
        st.warning(
            "No patterns passed the "
            "sample requirements."
        )
        st.stop()

    results = results.sort_values(
        [
            "Training lift pp",
            "Training matches"
        ],
        ascending=[
            False,
            False
        ]
    ).reset_index(drop=True)

    st.subheader(
        "Automatically discovered patterns"
    )

    st.dataframe(
        results,
        use_container_width=True,
        hide_index=True
    )

    st.download_button(
        "Download pattern results",
        data=results.to_csv(
            index=False
        ),
        file_name=(
            "starlizard_pattern_discovery.csv"
        ),
        mime="text/csv"
    )

    st.subheader(
        "Research interpretation"
    )

    st.write(
        "Training lift measures how much "
        "a historical pattern exceeds "
        "the overall training hit rate."
    )

    st.write(
        "Test fair odds are calculated "
        "from the observed success rate "
        "in later matches. They are "
        "descriptive estimates, not "
        "bookmaker prices."
    )

    st.warning(
        "Patterns can overlap and "
        "multiple comparisons can "
        "produce misleading findings. "
        "No betting edge is established "
        "until predictions are validated "
        "against actual market odds, "
        "commission and further unseen data."
    )

    st.caption(
        "Research-only model | "
        "Read-only database access | "
        "Existing collectors unaffected"
    )

except Exception as error:

    st.error(
        "Pattern Discovery Lab could not load."
    )

    st.exception(error)
