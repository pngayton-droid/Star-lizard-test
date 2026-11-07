
import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

API_BASE = "https://api.thestatsapi.com/api"
UK = ZoneInfo("Europe/London")
KEY_NAMES = (
    "STATS_API_KEY",
    "THESTATSAPI_KEY",
    "THE_STATS_API_KEY",
    "THESTATS_API_KEY",
    "STATSAPI_KEY",
)

@st.cache_data(ttl=300, show_spinner=False)
def fixtures_for_day(key, day):
    rows = []
    for page in range(1, 21):
        response = requests.get(
            API_BASE + "/football/matches",
            headers={"Authorization": "Bearer " + key},
            params={
                "date_from": day,
                "date_to": day,
                "sort": "utc_date",
                "per_page": 100,
                "page": page,
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        rows.extend(payload.get("data") or [])
        total_pages = int(
            (payload.get("meta") or {}).get("total_pages") or 1
        )
        if page >= total_pages:
            return rows
    raise RuntimeError(
        "Fixture results exceeded 20 pages; narrow the date range."
    )

@st.cache_data(ttl=60, show_spinner=False)
def fetch_live_stats(key, match_id):
    response = requests.get(
        API_BASE + "/football/matches/" + match_id + "/live-stats",
        headers={"Authorization": "Bearer " + key},
        timeout=20,
    )
    if response.status_code == 409:
        return None
    response.raise_for_status()
    return response.json().get("data")

def kickoff(item):
    raw = item.get("utc_date")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(
            raw.replace("Z", "+00:00")
        ).astimezone(UK)
    except ValueError:
        return None

def team_name(item, side):
    return (
        (item.get(side + "_team") or {}).get("name")
        or "Unknown"
    )

def label(item):
    start = kickoff(item)
    time = start.strftime("%H:%M") if start else "--:--"
    score = item.get("score") or {}
    h, a = score.get("home"), score.get("away")
    result = (
        f" [{h}-{a}]"
        if h is not None and a is not None
        else ""
    )
    return (
        f"{time}  {team_name(item, 'home')} v "
        f"{team_name(item, 'away')}{result}  "
        f"({item.get('status', 'unknown')})"
    )

def exact_match(api_name, find_team_names):
    matches = find_team_names(api_name[:5])
    exact = next(
        (
            name for name in matches
            if name.casefold() == api_name.casefold()
        ),
        None,
    )
    return exact, matches

def render_live_fixtures(
    leagues, find_team_names, show_comparison
):
    st.header("⚽ Live Fixtures")
    st.caption(
        "TheStatsAPI fixtures and live scores; "
        "Supabase historical analysis."
    )

    key = next(
        (
            st.secrets.get(name)
            for name in KEY_NAMES
            if st.secrets.get(name)
        ),
        None,
    )

    if not key:
        st.warning(
            "TheStatsAPI key is not configured "
            "in this Streamlit app."
        )
        st.info(
            "Add the existing key to Streamlit secrets "
            "as STATS_API_KEY. "
            "Do not put the key in GitHub code."
        )
        return

    today = datetime.now(UK).date()
    day = st.date_input(
        "Fixture date (UK)",
        today,
        min_value=today - timedelta(days=7),
        max_value=today + timedelta(days=14),
        key="lf_date",
    )

    chosen = st.multiselect(
        "Leagues",
        list(leagues),
        default=list(leagues),
        format_func=lambda code: leagues[code],
        key="lf_leagues",
    )

    if st.button(
        "🔄 Refresh fixture data", key="lf_refresh"
    ):
        fixtures_for_day.clear()
        fetch_live_stats.clear()

    if not chosen:
        st.info("Choose at least one league.")
        return

    try:
        with st.spinner("Fetching fixtures..."):
            found = []
            for query_day in (
                day - timedelta(days=1),
                day,
                day + timedelta(days=1),
            ):
                found.extend(
                    fixtures_for_day(
                        key, query_day.isoformat()
                    )
                )
    except (
        requests.RequestException,
        ValueError,
        RuntimeError,
    ) as exc:
        st.error(
            f"Fixtures could not be retrieved: {exc}"
        )
        return

    by_id = {}
    for item in found:
        start = kickoff(item)
        if (
            item.get("competition_id") in chosen
            and start is not None
            and start.date() == day
            and item.get("id")
        ):
            by_id[item["id"]] = item

    matches = sorted(
        by_id.values(),
        key=lambda item: kickoff(item),
    )

    st.caption(
        f"{len(matches)} matches found · "
        "UK kick-off times · "
        "5-minute fixture cache"
    )

    if not matches:
        st.info(
            "No fixtures found for these leagues "
            "on this date."
        )
        return

    selected = st.selectbox(
        "Select a match",
        matches,
        format_func=label,
        key="lf_match",
    )

    home_api = team_name(selected, "home")
    away_api = team_name(selected, "away")

    st.subheader(f"{home_api} v {away_api}")
    st.caption(
        f"{leagues.get(selected.get('competition_id'), 'League')}"
        f" · {selected.get('status', 'unknown')}"
    )

    if selected.get("status") == "live":
        try:
            snapshot = fetch_live_stats(
                key, selected["id"]
            )

            if snapshot:
                meta = snapshot.get("meta") or {}

                st.write(
                    f"Minute: "
                    f"{meta.get('elapsed_minutes', '—')}"
                    f" · Score: "
                    f"{meta.get('home_goals', '—')}-"
                    f"{meta.get('away_goals', '—')}"
                )

                stats = snapshot.get("stats") or {}
                rows = []

                for title, field in [
                    ("Shots", "total_shots"),
                    ("Shots on target", "shots_on_target"),
                    ("Corners", "corner_kicks"),
                    ("Yellow cards", "yellow_cards"),
                    ("Red cards", "red_cards"),
                    ("xG", "expected_goals"),
                ]:
                    values = (
                        (stats.get(field) or {})
                        .get("all") or {}
                    )

                    if (
                        values.get("home") is not None
                        or values.get("away") is not None
                    ):
                        rows.append({
                            "Statistic": title,
                            home_api: values.get("home"),
                            away_api: values.get("away"),
                        })

                if rows:
                    st.dataframe(
                        pd.DataFrame(rows),
                        hide_index=True,
                        width="stretch",
                    )
                else:
                    st.info(
                        "Detailed live statistics "
                        "are not available for this match."
                    )
            else:
                st.info(
                    "Live statistics are "
                    "temporarily unavailable."
                )

        except requests.RequestException:
            st.warning(
                "Live statistics request failed."
            )

    st.header(
        "Historical comparison and potential angles"
    )
    st.caption(
        "Only league matches played before "
        "the selected fixture date are included. "
        "Historical rates are not predicted probabilities."
    )

    try:
        home, home_options = exact_match(
            home_api, find_team_names
        )
        away, away_options = exact_match(
            away_api, find_team_names
        )
    except Exception as exc:
        st.error(
            "Database team lookup failed: "
            f"{type(exc).__name__}"
        )
        return

    if home is None:
        st.warning(
            f"Confirm historical name for {home_api}."
        )
        choice = st.selectbox(
            "Home database team",
            ["Select a team"] + home_options,
            key="lf_home_map",
        )
        home = (
            choice
            if choice != "Select a team"
            else None
        )

    if away is None:
        st.warning(
            f"Confirm historical name for {away_api}."
        )
        choice = st.selectbox(
            "Away database team",
            ["Select a team"] + away_options,
            key="lf_away_map",
        )
        away = (
            choice
            if choice != "Select a team"
            else None
        )

    c1, c2 = st.columns(2)

    with c1:
        home_count = st.selectbox(
            "Home matches",
            [5, 10, 15, 20, 25],
            index=1,
            key="lf_hn",
        )

    with c2:
        away_count = st.selectbox(
            "Away matches",
            [5, 10, 15, 20, 25],
            index=1,
            key="lf_an",
        )

    selection = (
        selected["id"],
        home,
        away,
        home_count,
        away_count,
    )

    if st.button(
        "📊 Analyse this fixture",
        type="primary",
        width="stretch",
        disabled=not (
            home and away and home != away
        ),
        key="lf_analyse",
    ):
        st.session_state["lf_selection"] = selection

    if (
        st.session_state.get("lf_selection")
        == selection
    ):
        cutoff = (
            day - timedelta(days=1)
        ).isoformat()

        try:
            show_comparison(
                home,
                away,
                home_count,
                away_count,
                20,
                cutoff,
            )
        except Exception as exc:
            st.error(
                "Comparison failed: "
                f"{type(exc).__name__}"
            )
