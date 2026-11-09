
import sys
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

# Import our quality module from the repository root.
ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_quality import add_quality_columns


st.set_page_config(
    page_title="Scrumpy Data Quality Test",
    layout="wide",
)

st.title("🦎 Scrumpy — Data Quality Test")

st.caption(
    "Read-only historical data audit. "
    "No database writes or StatsAPI requests."
)


EXPECTED = {
    "corners": 11309,
    "yellow_cards": 11541,
    "red_cards": 11716,
}

EXPECTED_ACTIVE_MATCHES = 11745
EXCLUDED_COMPETITION = "comp_6387"


def get_secret(*names):
    """Find an existing Streamlit secret safely."""
    for name in names:
        try:
            value = st.secrets.get(name)
            if value:
                return str(value)
        except Exception:
            pass

    return None


@st.cache_data(ttl=600, show_spinner=False)
def load_records():
    """Read historical records without modifying Supabase."""

    url = get_secret(
        "SUPABASE_URL",
        "supabase_url",
    )

    key = get_secret(
        "SUPABASE_SECRET_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_KEY",
        "supabase_key",
    )

    if not url or not key:
        raise RuntimeError(
            "Supabase connection settings not found "
            "in Streamlit secrets."
        )

    base = url.rstrip("/") + "/rest/v1"

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }

    def fetch_table(table, columns):
        """Fetch all rows in small batches."""

        rows = []
        page_size = 500
        offset = 0

        while True:
            response = requests.get(
                f"{base}/{table}",
                headers={
                    **headers,
                    "Range": (
                        f"{offset}-"
                        f"{offset + page_size - 1}"
                    ),
                },
                params={
                    "select": columns,
                    "order": "match_id.asc",
                },
                timeout=60,
            )

            response.raise_for_status()

            batch = response.json()

            if not isinstance(batch, list):
                raise RuntimeError(
                    f"Unexpected response from {table}"
                )

            rows.extend(batch)

            if len(batch) < page_size:
                break

            offset += len(batch)

        return pd.DataFrame(rows)

    xg = fetch_table(
        "historical_xg",
        "match_id,competition_id",
    )

    events = fetch_table(
        "historical_match_events",
        "match_id,stats_data,timeline_data,"
        "corners_match,yellow_cards_match,"
        "red_cards_match",
    )

    if xg.empty or events.empty:
        raise RuntimeError(
            "Historical records were not found."
        )

    if xg["match_id"].duplicated().any():
        raise RuntimeError(
            "Duplicate match IDs in historical_xg."
        )

    if events["match_id"].duplicated().any():
        raise RuntimeError(
            "Duplicate match IDs in historical_match_events."
        )

    merged = xg.merge(
        events,
        on="match_id",
        how="inner",
        validate="one_to_one",
    )

    return merged


def run_test(df):
    """Apply the actual Python quality rules."""

    checked = add_quality_columns(
        df,
        markets=(
            "corners",
            "yellow_cards",
            "red_cards",
        ),
    )

    active = checked[
        checked["competition_id"]
        != EXCLUDED_COMPETITION
    ].copy()

    st.subheader("Database coverage")

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Joined matches",
        f"{len(df):,}",
    )

    col2.metric(
        "Scotland excluded",
        f"{len(df) - len(active):,}",
    )

    col3.metric(
        "Active matches",
        f"{len(active):,}",
    )

    results = []

    for market, expected in EXPECTED.items():

        quality_column = f"{market}_quality"
        usable_column = f"{market}_totals_usable"
        timing_column = f"{market}_timing_usable"

        verified = int(
            (
                active[quality_column]
                == "timeline_verified"
            ).sum()
        )

        partial = int(
            (
                active[quality_column]
                == "partial_totals_only"
            ).sum()
        )

        usable = int(
            active[usable_column].sum()
        )

        timing = int(
            active[timing_column].sum()
        )

        excluded = len(active) - usable

        results.append({
            "Market": market,
            "Verified": verified,
            "Partial": partial,
            "Usable": usable,
            "Timing usable": timing,
            "Excluded": excluded,
            "Expected": expected,
            "Difference": usable - expected,
            "Result": (
                "PASS"
                if usable == expected
                else "CHECK"
            ),
        })

    result_df = pd.DataFrame(results)

    st.subheader("Quality test results")

    st.dataframe(
        result_df,
        hide_index=True,
        use_container_width=True,
    )

    all_pass = (
        all(
            result["Result"] == "PASS"
            for result in results
        )
        and len(active) == EXPECTED_ACTIVE_MATCHES
    )

    if all_pass:
        st.success(
            "ALL THREE MARKETS PASS! "
            "Python matches our Supabase benchmarks."
        )
    else:
        st.warning(
            "One or more results differ from "
            "our previous Supabase audit. "
            "Do not connect the filters "
            "to the pricing model yet."
        )

    st.subheader("Competition breakdown")

    league_rows = []

    for competition, group in active.groupby(
        "competition_id"
    ):

        league_rows.append({
            "Competition": competition,
            "Matches": len(group),
            "Corners": int(
                group["corners_totals_usable"].sum()
            ),
            "Yellow cards": int(
                group["yellow_cards_totals_usable"].sum()
            ),
            "Red cards": int(
                group["red_cards_totals_usable"].sum()
            ),
        })

    st.dataframe(
        pd.DataFrame(league_rows),
        hide_index=True,
        use_container_width=True,
    )

    st.info(
        "This test only reads Supabase data. "
        "No historical records, verification "
        "flags or model parameters are changed."
    )


if st.button(
    "Run quality test",
    type="primary",
):

    with st.spinner(
        "Loading and checking historical matches..."
    ):
        try:
            records = load_records()
            run_test(records)

        except requests.HTTPError as exc:
            status = (
                exc.response.status_code
                if exc.response is not None
                else "unknown"
            )
            st.error(
                f"Supabase request failed. "
                f"HTTP status: {status}"
            )

        except Exception as exc:
            st.error(
                f"Quality test could not complete: {exc}"
            )
