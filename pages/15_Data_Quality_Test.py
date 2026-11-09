
import sys
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

# Allow imports from the repository root.
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
    "Read-only Supabase audit. "
    "No database writes or StatsAPI requests."
)

EXPECTED = {
    "corners": 11309,
    "yellow_cards": 11541,
    "red_cards": 11716,
}

EXCLUDED_COMPETITION = "comp_6387"


def get_secret(*names):
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
    url = get_secret("SUPABASE_URL", "supabase_url")
    key = get_secret(
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_KEY",
        "supabase_key",
    )

    if not url or not key:
        raise RuntimeError(
            "Supabase URL or key not found in Streamlit secrets."
        )

    base = url.rstrip("/") + "/rest/v1"

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }

    def fetch_table(table, columns):
        rows = []
        page_size = 500

        while True:
            start = len(rows)
            end = start + page_size - 1

            response = requests.get(
                f"{base}/{table}",
                headers={
                    **headers,
                    "Range": f"{start}-{end}",
                },
                params={"select": columns},
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

        return pd.DataFrame(rows)

    xg = fetch_table(
        "historical_xg",
        "match_id,competition_id",
    )

    events = fetch_table(
        "historical_match_events",
        "match_id,stats_data,timeline_data,"
        "corners_match,yellow_cards_match,red_cards_match",
    )

    if xg.empty or events.empty:
        raise RuntimeError("Historical records not found.")

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


if st.button("Run quality test", type="primary"):

    with st.spinner("Checking historical records..."):
        try:
            df = load_records()

            st.write(
                f"Joined historical matches: {len(df):,}"
            )

            scotland = df[
                df["competition_id"]
                == EXCLUDED_COMPETITION
            ]

            st.write(
                f"Scottish matches excluded: {len(scotland):,}"
            )

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

            st.write(
                f"Matches across active leagues: "
                f"{len(active):,}"
            )

            results = []

            for market, expected in EXPECTED.items():
                actual = int(
                    active[
                        f"{market}_totals_usable"
                    ].sum()
                )

                verified = int(
                    (
                        active[f"{market}_quality"]
                        == "timeline_verified"
                    ).sum()
                )

                partial = int(
                    (
                        active[f"{market}_quality"]
                        == "partial_totals_only"
                    ).sum()
                )

                results.append({
                    "Market": market,
                    "Timeline verified": verified,
                    "Partial totals": partial,
                    "Usable": actual,
                    "Expected": expected,
                    "Difference": actual - expected,
                    "Result": (
                        "PASS"
                        if actual == expected
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

            if all(
                row["Result"] == "PASS"
                for row in results
            ) and len(active) == 11745:
                st.success(
                    "All three markets match the "
                    "Supabase benchmark!"
                )
            else:
                st.warning(
                    "One or more results differ. "
                    "Investigate before connecting "
                    "the filters to the model."
                )

            st.subheader("Coverage by league")

            league_rows = []

            for league, group in active.groupby(
                "competition_id"
            ):
                league_rows.append({
                    "Competition": league,
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

        except Exception as exc:
            st.error(
                f"Quality test could not complete: {exc}"
            )
