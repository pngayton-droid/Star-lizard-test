
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
    "No bookmaker API calls | Read-only database access"
)


def get_secret(*names):
    for name in names:
        try:
            value = st.secrets.get(name)
            if value:
                return value
        except Exception:
            pass

    try:
        section = st.secrets.get("supabase", {})
        for name in names:
            value = section.get(name)
            if value:
                return value
    except Exception:
        pass

    return None


@st.cache_data(ttl=3600, show_spinner=False)
def load_matches():
    url = get_secret(
        "SUPABASE_URL", "supabase_url", "url"
    )
    key = get_secret(
        "SUPABASE_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_ANON_KEY",
        "supabase_key",
        "key",
    )

    if not url or not key:
        raise ValueError(
            "Supabase credentials were not found "
            "in Streamlit secrets."
        )

    db = create_client(url, key)

    columns = (
        "match_id,match_date,home_team,away_team,"
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
            query = query.gt("match_id", last_id)

        result = query.execute()
        batch = result.data or []

        if not batch:
            break

        records.extend(batch)
        last_id = batch[-1]["match_id"]

        if len(batch) < 500:
            break

    return pd.DataFrame(records)


def wilson_lower(hits, total):
    if total <= 0:
        return 0.0

    z = 1.96
    p = hits / total
    denominator = 1 + z * z / total

    centre = p + z * z / (2 * total)
    margin = z * np.sqrt(
        p * (1 - p) / total
        + z * z / (4 * total * total)
    )

    return (centre - margin) / denominator


def prepare_data(df):
    numeric = [
        "home_ht_goals", "away_ht_goals",
        "home_goals", "away_goals",
        "home_ht_xg", "away_ht_xg",
    ]

    for column in numeric:
        df[column] = pd.to_numeric(
            df[column], errors="coerce"
        )

    df["match_date"] = pd.to_datetime(
        df["match_date"], errors="coerce"
    )

    df = df.dropna(
        subset=numeric + ["match_date"]
    ).copy()

    df = df[
        (df["home_ht_xg"] >= 0)
        & (df["away_ht_xg"] >= 0)
        & (df["home_goals"] >= df["home_ht_goals"])
        & (df["away_goals"] >= df["away_ht_goals"])
        & (df["home_ht_goals"] != df["away_ht_goals"])
    ].copy()

    df = df.sort_values(
        ["match_date", "match_id"]
    ).reset_index(drop=True)

    df["trailing_side"] = np.where(
        df["home_ht_goals"] < df["away_ht_goals"],
        "Home", "Away"
    )

    df["deficit"] = abs(
        df["home_ht_goals"] - df["away_ht_goals"]
    )

    home_trailing = df["trailing_side"] == "Home"

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

    trailing_second_half_goals = np.where(
        home_trailing,
        df["home_goals"] - df["home_ht_goals"],
        df["away_goals"] - df["away_ht_goals"],
    )

    df["scored_second_half"] = (
        trailing_second_half_goals > 0
    ).astype(int)

    df["xg_band"] = pd.cut(
        df["trailing_xg"],
        bins=[-0.001, 0.2, 0.4, 0.8, 1.2, np.inf],
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
        bins=[-np.inf, -0.5, 0, 0.5, np.inf],
        labels=[
            "Outplayed by 0.50+ xG",
            "Behind on xG",
            "Ahead by under 0.50 xG",
            "Ahead by 0.50+ xG",
        ],
        right=False,
    )

    return df


def discover_patterns(train, test, minimum):
    dimensions = [
        ["trailing_side", "deficit"],
        ["trailing_side", "xg_band"],
        ["trailing_side", "dominance"],
        ["trailing_side", "deficit", "xg_band"],
        ["trailing_side", "deficit", "dominance"],
    ]

    baseline = train["scored_second_half"].mean()
    results = []

    for fields in dimensions:
        for keys, group in train.groupby(
            fields, observed=True
        ):
            if not isinstance(keys, tuple):
                keys = (keys,)

            n = len(group)

            if n < minimum:
                continue

            mask = pd.Series(
                True, index=test.index
            )

            for field, value in zip(fields, keys):
                mask &= test[field] == value

            holdout = test.loc[mask]

            if len(holdout) < 30:
                continue

            hits = int(group["scored_second_half"].sum())
            rate = hits / n

            test_hits = int(
                holdout["scored_second_half"].sum()
            )
            test_rate = test_hits / len(holdout)

            description = " | ".join(
                f"{field.replace('_', ' ')}: {value}"
                for field, value in zip(fields, keys)
            )

            results.append({
                "Pattern": description,
                "Training matches": n,
                "Training hit %": round(rate * 100, 2),
                "Test matches": len(holdout),
                "Test hit %": round(test_rate * 100, 2),
                "Test fair odds": (
                    round(1 / test_rate, 2)
                    if test_rate > 0 else np.nan
                ),
                "Test lower 95% %": round(
                    wilson_lower(
                        test_hits, len(holdout)
                    ) * 100, 2
                ),
                "Training lift pp": round(
                    (rate - baseline) * 100, 2
                ),
            })

    return pd.DataFrame(results), baseline


try:
    with st.spinner("Loading historical matches..."):
        raw = load_matches()

    if raw.empty:
        st.warning("No historical records returned.")
        st.stop()

    data = prepare_data(raw)

    st.metric("Usable trailing-team matches", len(data))

    st.info(
        "Version 1 studies whether the team trailing "
        "at half-time scores at least once in the "
        "second half. It does NOT yet study which "
        "team scores the first second-half goal."
    )

    if len(data) < 300:
        st.warning(
            "Not enough usable matches for this test."
        )
        st.stop()

    split = int(len(data) * 0.70)

    train = data.iloc[:split].copy()
    test = data.iloc[split:].copy()

    st.write(
        f"Training: {len(train):,} matches | "
        f"Later testing: {len(test):,} matches"
    )

    minimum = st.slider(
        "Minimum training sample per pattern",
        min_value=50,
        max_value=500,
        value=150,
        step=50,
    )

    results, baseline = discover_patterns(
        train, test, minimum
    )

    st.metric(
        "Training baseline: trailing team scores in 2H",
        f"{baseline * 100:.2f}%"
    )

    st.caption(
        "Baseline includes all trailing teams in the "
        "training sample. Comparisons are descriptive "
        "and are not adjusted for all match factors."
    )

    if results.empty:
        st.warning(
            "No patterns passed the sample thresholds."
        )
        st.stop()

    st.subheader("Automatically discovered patterns")

    st.caption(
        "Patterns are selected using earlier matches. "
        "The later-match results are displayed for "
        "evaluation, not used to select the patterns."
    )

    results = results.sort_values(
        ["Training lift pp", "Training matches"],
        ascending=[False, False],
    ).reset_index(drop=True)

    st.dataframe(
        results,
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download research results CSV",
        data=results.to_csv(index=False),
        file_name="starlizard_pattern_discovery.csv",
        mime="text/csv",
    )

    st.subheader("Research notes")

    st.write(
        "A higher historical strike rate is not "
        "automatically a betting advantage. "
        "We still need actual market prices, "
        "commission, calibration, and further "
        "out-of-sample testing."
    )

    st.write(
        "Patterns overlap, and testing many patterns "
        "can create misleading apparent discoveries. "
        "These findings should be treated as "
        "candidates for further validation."
    )

    st.caption(
        "No historical records were modified. "
        "No external football API was called."
    )

except Exception as exc:
    st.error("Pattern Discovery Lab could not load.")
    st.exception(exc)
