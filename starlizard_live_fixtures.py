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


def uk_time():
    return datetime.now(UK).strftime(
        "%Y-%m-%d %H:%M:%S %Z"
    )


def get_key():
    for name in KEY_NAMES:
        key = st.secrets.get(name)
        if key:
            return str(key).strip()
    return None


def api_request(key, path, params=None):
    started = uk_time()

    response = requests.get(
        API_BASE + path,
        headers={
            "Authorization": f"Bearer {key}",
            "Cache-Control": "no-cache",
        },
        params=params,
        timeout=25,
    )

    received = uk_time()
    response.raise_for_status()

    return {
        "body": response.json(),
        "started": started,
        "received": received,
        "status": response.status_code,
        "http_date": response.headers.get("Date"),
        "age": response.headers.get("Age"),
        "cache_control": response.headers.get(
            "Cache-Control"
        ),
    }


@st.cache_data(ttl=300, show_spinner=False)
def fixtures_for_day(key, day):
    rows = []

    for page in range(1, 21):
        result = api_request(
            key,
            "/football/matches",
            {
                "date_from": day,
                "date_to": day,
                "sort": "utc_date",
                "per_page": 100,
                "page": page,
            },
        )

        payload = result["body"]
        rows.extend(payload.get("data") or [])

        pages = int(
            (payload.get("meta") or {}).get(
                "total_pages"
            ) or 1
        )

        if page >= pages:
            return rows

    raise RuntimeError(
        "Fixture results exceeded 20 pages."
    )


@st.cache_data(ttl=60, show_spinner=False)
def fetch_live_stats(key, match_id):
    response = requests.get(
        API_BASE
        + f"/football/matches/{match_id}/live-stats",
        headers={
            "Authorization": f"Bearer {key}"
        },
        timeout=25,
    )

    if response.status_code == 409:
        return None

    response.raise_for_status()
    return response.json().get("data") or {}


def kickoff(item):
    raw = item.get("utc_date")

    if not raw:
        return None

    try:
        return datetime.fromisoformat(
            raw.replace("Z", "+00:00")
        ).astimezone(UK)
    except (ValueError, TypeError):
        return None


def team_name(item, side):
    return (
        (item.get(side + "_team") or {}).get("name")
        or "Unknown"
    )


def fixture_label(item):
    start = kickoff(item)
    clock = (
        start.strftime("%H:%M")
        if start else "--:--"
    )

    score = item.get("score") or {}
    home = score.get("home")
    away = score.get("away")

    score_text = (
        f" [{home}-{away}]"
        if home is not None and away is not None
        else ""
    )

    return (
        f"{clock} "
        f"{team_name(item, 'home')} v "
        f"{team_name(item, 'away')}"
        f"{score_text} "
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


def show_live_stats(snapshot, home, away):
    if not snapshot:
        st.info("Live statistics unavailable.")
        return

    meta = snapshot.get("meta") or {}

    st.write(
        f"Minute: {meta.get('elapsed_minutes', '—')}"
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
            (stats.get(field) or {}).get("all")
            or {}
        )

        if (
            values.get("home") is not None
            or values.get("away") is not None
        ):
            rows.append({
                "Statistic": title,
                home: values.get("home"),
                away: values.get("away"),
            })

    if rows:
        st.dataframe(
            pd.DataFrame(rows),
            hide_index=True,
            width="stretch",
        )


def show_diagnostics(key, match_id):
    st.subheader("🔍 Live feed diagnostics")

    st.caption(
        "Fresh HTTP requests bypassing "
        "Streamlit's cached match data."
    )

    try:
        with st.spinner(
            "Checking both API endpoints..."
        ):
            match_result = api_request(
                key,
                f"/football/matches/{match_id}",
            )

            stats_result = api_request(
                key,
                f"/football/matches/"
                f"{match_id}/live-stats",
            )

    except requests.RequestException as exc:
        st.error(
            f"Diagnostic request failed: {exc}"
        )
        return

    match = (
        match_result["body"].get("data") or {}
    )
    stats = (
        stats_result["body"].get("data") or {}
    )

    score = match.get("score") or {}
    live = match.get("live") or {}
    meta = stats.get("meta") or {}

    st.write("**Match ID:**", match_id)

    st.write(
        "**Teams:**",
        team_name(match, "home"),
        "v",
        team_name(match, "away"),
    )

    st.write(
        "**Match status:**",
        match.get("status"),
    )

    st.dataframe(
        pd.DataFrame([
            {
                "Source": "Match details",
                "Score": (
                    f"{score.get('home', '—')}-"
                    f"{score.get('away', '—')}"
                ),
                "Minute": live.get(
                    "elapsed_minutes", "—"
                ),
                "Received UK": match_result[
                    "received"
                ],
            },
            {
                "Source": "Live statistics",
                "Score": (
                    f"{meta.get('home_goals', '—')}-"
                    f"{meta.get('away_goals', '—')}"
                ),
                "Minute": meta.get(
                    "elapsed_minutes", "—"
                ),
                "Received UK": stats_result[
                    "received"
                ],
            },
        ]),
        hide_index=True,
        width="stretch",
    )

    st.subheader("HTTP response information")

    st.dataframe(
        pd.DataFrame([
            {
                "Source": "Match details",
                "HTTP Date": match_result[
                    "http_date"
                ],
                "Age": match_result["age"],
                "Cache-Control": match_result[
                    "cache_control"
                ],
            },
            {
                "Source": "Live statistics",
                "HTTP Date": stats_result[
                    "http_date"
                ],
                "Age": stats_result["age"],
                "Cache-Control": stats_result[
                    "cache_control"
                ],
            },
        ]),
        hide_index=True,
        width="stretch",
    )

    with st.expander(
        "Additional API timestamps and metadata"
    ):
        st.write(
            "Fixture live metadata:", live
        )
        st.write(
            "Live statistics metadata:", meta
        )
        st.write(
            "Match response fields:",
            list(match.keys()),
        )
        st.write(
            "Statistics response fields:",
            list(stats.keys()),
        )

    st.warning(
        "A fresh HTTP response does not "
        "guarantee fresh underlying match data. "
        "Compare the score and minute against "
        "an independent live source."
    )


def render_live_fixtures(
    leagues,
    find_team_names,
    show_comparison,
):
    st.header("⚽ Live Fixtures")

    st.caption(
        "TheStatsAPI live fixtures and "
        "Supabase historical analysis."
    )

    key = get_key()

    if not key:
        st.warning(
            "TheStatsAPI key is missing "
            "from Streamlit secrets."
        )
        return

    today = datetime.now(UK).date()

    day = st.date_input(
        "Fixture date (UK)",
        value=today,
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
        "🔄 Refresh fixture data",
        key="lf_refresh",
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
                        key,
                        query_day.isoformat(),
                    )
                )

    except (
        requests.RequestException,
        RuntimeError,
        ValueError,
    ) as exc:
        st.error(
            f"Fixture retrieval failed: {exc}"
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
        key=kickoff,
    )

    st.caption(
        f"{len(matches)} fixtures found "
        "· UK kick-off times"
    )

    if not matches:
        st.info(
            "No matches found for this date."
        )
        return

    selected = st.selectbox(
        "Select a match",
        matches,
        format_func=fixture_label,
        key="lf_match",
    )

    home_api = team_name(
        selected, "home"
    )
    away_api = team_name(
        selected, "away"
    )

    match_id = selected["id"]

    st.subheader(
        f"{home_api} v {away_api}"
    )

    st.caption(
        leagues.get(
            selected.get("competition_id"),
            "League",
        )
    )

    if selected.get("status") == "live":
        try:
            snapshot = fetch_live_stats(
                key, match_id
            )
            show_live_stats(
                snapshot, home_api, away_api
            )
        except requests.RequestException as exc:
            st.warning(
                f"Live stats unavailable: {exc}"
            )

    st.divider()

    if st.button(
        "🔍 Diagnose live feed freshness",
        type="primary",
        width="stretch",
        key="lf_diagnose",
    ):
        show_diagnostics(key, match_id)

    st.divider()

    st.header(
        "Historical comparison "
        "and potential angles"
    )

    st.caption(
        "League matches before the "
        "selected fixture date only."
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
            "Historical team lookup failed: "
            f"{type(exc).__name__}"
        )
        return

    if home is None:
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
        match_id,
        home,
        away,
        home_count,
        away_count,
    )

    if st.button(
        "📊 Analyse this fixture",
        width="stretch",
        disabled=not (
            home and away and home != away
        ),
        key="lf_analyse",
    ):
        st.session_state[
            "lf_selection"
        ] = selection

    if (
        st.session_state.get(
            "lf_selection"
        ) == selection
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
                "Historical analysis failed: "
                f"{type(exc).__name__}"
            )
