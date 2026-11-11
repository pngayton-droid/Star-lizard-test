
"""
PRO STARLIZARD V5.7
Live Fixtures + Automatic Halftime Pricing
+ Historical Match Audit

Uses TheStatsAPI and read-only Supabase.

Features:
- Automatic UK-date fixture discovery
- Match details and statistics
- Verified first-half inputs
- Historical corners and cards pricing
- Individual historical match audit
- Audit CSV downloads
- Results retained across Streamlit reruns

Historical frequencies are not calibrated
fair odds or demonstrated betting edges.
"""

import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st
from supabase import create_client

from starlizard_halftime_markets_v57 import (
    candidates_query,
    collect,
    market_table,
    render_audit,
    MIN_SAMPLE,
)


API_BASE = "https://api.thestatsapi.com/api"
UK = ZoneInfo("Europe/London")

KEY_NAMES = (
    "STATS_API_KEY",
    "THESTATSAPI_KEY",
    "THE_STATS_API_KEY",
    "THESTATS_API_KEY",
    "STATSAPI_KEY",
)

LIVE_RESULTS_KEY = "lf_historical_audit_results"


# ==========================================
# API CONNECTION
# ==========================================

def get_key():
    for name in KEY_NAMES:
        value = st.secrets.get(name)
        if value:
            return str(value).strip()
    return None


def api_request(key, path, params=None):
    response = requests.get(
        API_BASE + path,
        headers={
            "Authorization": f"Bearer {key}",
            "Cache-Control": "no-cache",
        },
        params=params,
        timeout=25,
    )

    if response.status_code in (404, 409):
        return {
            "data": None,
            "status": response.status_code,
        }

    response.raise_for_status()

    body = response.json()

    return {
        "data": (
            body.get("data")
            if isinstance(body, dict)
            else None
        ),
        "status": response.status_code,
    }


# ==========================================
# FIXTURE DISCOVERY
# ==========================================

@st.cache_data(ttl=300, show_spinner=False)
def fixtures_for_day(key, day):
    rows = []

    for page in range(1, 21):
        response = requests.get(
            API_BASE + "/football/matches",
            headers={
                "Authorization": f"Bearer {key}"
            },
            params={
                "date_from": day,
                "date_to": day,
                "sort": "utc_date",
                "per_page": 100,
                "page": page,
            },
            timeout=25,
        )

        response.raise_for_status()
        payload = response.json()

        rows.extend(payload.get("data") or [])

        pages = int(
            (payload.get("meta") or {}).get(
                "total_pages"
            ) or 1
        )

        if page >= pages:
            return rows

    raise RuntimeError(
        "Fixture results exceeded "
        "the 20-page safety limit."
    )


@st.cache_data(ttl=60, show_spinner=False)
def match_payload(key, match_id, kind):
    suffix = {
        "details": "",
        "live": "/live-stats",
        "historical": "/stats",
    }[kind]

    return api_request(
        key,
        f"/football/matches/{match_id}{suffix}",
    )


# ==========================================
# GENERAL HELPERS
# ==========================================

def kickoff(item):
    raw = item.get("utc_date")

    if not raw:
        return None

    try:
        return datetime.fromisoformat(
            str(raw).replace("Z", "+00:00")
        ).astimezone(UK)

    except (ValueError, TypeError):
        return None


def team_name(item, side):
    team = item.get(side + "_team") or {}

    if isinstance(team, dict):
        return str(
            team.get("name") or "Unknown"
        )

    return str(team)


def fixture_label(item):
    start = kickoff(item)

    clock = (
        start.strftime("%H:%M")
        if start
        else "--:--"
    )

    score = item.get("score") or {}

    home = score.get("home")
    away = score.get("away")

    score_text = (
        f" [{home}-{away}]"
        if home is not None
        and away is not None
        else ""
    )

    return (
        f"{clock} "
        f"{team_name(item, 'home')} v "
        f"{team_name(item, 'away')}"
        f"{score_text} "
        f"({item.get('status', 'unknown')})"
    )


def numeric(value):
    if isinstance(value, bool):
        return None

    try:
        result = float(value)

        if math.isfinite(result):
            return result

        return None

    except (TypeError, ValueError):
        return None


def count(value):
    value = numeric(value)

    if (
        value is not None
        and value >= 0
        and value.is_integer()
    ):
        return int(value)

    return None


def pair(block):
    if not isinstance(block, dict):
        return None

    home = block.get("home")
    away = block.get("away")

    if (
        home is not None
        and away is not None
    ):
        return home, away

    return None


# ==========================================
# VERIFIED FIRST-HALF STATISTICS
# ==========================================

def period_pair(container, field):
    if not isinstance(container, dict):
        return None

    sources = [container]

    overview = container.get("overview")

    if isinstance(overview, dict):
        sources.append(overview)

    stats = container.get("stats")

    if isinstance(stats, dict):
        sources.append(stats)

        nested = stats.get("overview")

        if isinstance(nested, dict):
            sources.append(nested)

    for source in sources:
        item = source.get(field)

        if not isinstance(item, dict):
            continue

        for period in (
            "first_half",
            "firstHalf",
            "1h",
            "1st_half",
        ):
            values = pair(item.get(period))

            if values is not None:
                return values

    return None


def halftime_score(details, snapshot):
    """
    TheStatsAPI confirmed fields:
    score.half_time_home
    score.half_time_away

    Never substitute the current
    or full-time score.
    """

    for root in (details, snapshot):
        if not isinstance(root, dict):
            continue

        candidates = [
            root,
            root.get("score") or {},
            root.get("scores") or {},
            root.get("meta") or {},
        ]

        for source in candidates:
            if not isinstance(source, dict):
                continue

            for home_key, away_key in (
                (
                    "half_time_home",
                    "half_time_away",
                ),
                (
                    "home_ht_goals",
                    "away_ht_goals",
                ),
                (
                    "home_halftime_goals",
                    "away_halftime_goals",
                ),
            ):
                h = count(source.get(home_key))
                a = count(source.get(away_key))

                if h is not None and a is not None:
                    return h, a

            for name in (
                "half_time",
                "halftime",
                "ht",
                "halfTime",
                "first_half",
            ):
                values = pair(source.get(name))

                if values is not None:
                    h = count(values[0])
                    a = count(values[1])

                    if h is not None and a is not None:
                        return h, a

    return None


def extract_ht(details, snapshot):
    values = {
        "score": halftime_score(
            details,
            snapshot,
        )
    }

    for label, field, converter in (
        ("xg", "expected_goals", numeric),
        ("corners", "corner_kicks", count),
        ("yellows", "yellow_cards", count),
    ):
        raw = period_pair(snapshot, field)

        if raw is None:
            raw = period_pair(details, field)

        if raw is None:
            values[label] = None
            continue

        home = converter(raw[0])
        away = converter(raw[1])

        if (
            home is not None
            and away is not None
            and home >= 0
            and away >= 0
        ):
            values[label] = (home, away)
        else:
            values[label] = None

    return values


# ==========================================
# DATABASE CONNECTION
# ==========================================

@st.cache_resource
def get_db():
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_SECRET_KEY"],
    )


# ==========================================
# AUTOMATIC PRICING + AUDIT
# ==========================================

def show_prices(values, match_day, match_id):
    st.markdown(
        "### 🦎 Automatic halftime pricing"
    )

    signature = (
        str(match_id),
        match_day.isoformat(),
        repr(values),
    )

    saved = st.session_state.get(
        LIVE_RESULTS_KEY
    )

    if (
        saved is not None
        and saved.get("signature") != signature
    ):
        st.session_state.pop(
            LIVE_RESULTS_KEY,
            None,
        )
        saved = None

    missing = [
        name
        for name, value in values.items()
        if value is None
    ]

    if missing:
        st.warning(
            "Cannot calculate safely. Missing: "
            + ", ".join(missing)
            + "."
        )

        st.caption(
            "Full-time and current live totals "
            "are never substituted for "
            "first-half figures."
        )
        return

    hh, ah = values["score"]
    hx, ax = values["xg"]
    hc, ac = values["corners"]
    hy, ay = values["yellows"]

    st.success("First-half inputs available.")

    st.caption(
        f"HT {hh}-{ah} · "
        f"xG {hx:.2f}-{ax:.2f} · "
        f"corners {hc}-{ac} · "
        f"yellows {hy}-{ay}"
    )

    st.caption(
        "Matching tolerances: "
        "xG ±0.30 per team; "
        "corners ±2 combined; "
        "yellows ±1 combined."
    )

    calculate = st.button(
        "📊 Calculate halftime markets",
        type="primary",
        use_container_width=True,
        key="lf_price",
    )

    if calculate:
        st.session_state.pop(
            LIVE_RESULTS_KEY,
            None,
        )

        try:
            with st.spinner(
                "Calculating prices and "
                "collecting audit records..."
            ):
                db = get_db()

                candidates, capped = (
                    candidates_query(
                        db,
                        hh,
                        ah,
                        hx,
                        ax,
                        0.30,
                        match_day.isoformat(),
                    )
                )

                records, fetched, audit = collect(
                    db,
                    candidates,
                    hc,
                    ac,
                    2,
                    hy,
                    ay,
                    1,
                    False,
                    return_audit=True,
                )

            saved = {
                "signature": signature,
                "records": records,
                "audit": audit,
                "candidates": len(candidates),
                "fetched": fetched,
                "capped": capped,
            }

            st.session_state[
                LIVE_RESULTS_KEY
            ] = saved

        except Exception as exc:
            st.error(
                "Historical calculation failed: "
                f"{type(exc).__name__}: {exc}"
            )
            return

    if saved is None:
        return

    records = saved["records"]

    st.caption(
        f"{saved['candidates']} "
        "score/xG candidates · "
        f"{saved['fetched']} "
        "event records returned"
    )

    if saved["capped"]:
        st.warning(
            "The 3,000-match safety cap "
            "was reached. The sample is "
            "restricted to the latest matches."
        )

    for title, key, second_lines, full_lines in (
        (
            "🚩 Corners",
            "corners",
            [3.5, 4.5, 5.5, 6.5],
            [
                7.5, 8.5, 9.5,
                10.5, 11.5,
            ],
        ),
        (
            "🟨 Yellow cards",
            "yellows",
            [1.5, 2.5, 3.5, 4.5],
            [3.5, 4.5, 5.5, 6.5],
        ),
    ):
        sample = records[key]

        st.markdown(
            f"**{title} · "
            f"{len(sample)} comparable records**"
        )

        if len(sample) < MIN_SAMPLE:
            st.info(
                "Insufficient verified sample "
                "for pricing."
            )
            continue

        st.caption("Second half")

        st.dataframe(
            market_table(
                sample,
                second_lines,
                0,
            ),
            hide_index=True,
            use_container_width=True,
        )

        st.caption("Full match")

        st.dataframe(
            market_table(
                sample,
                full_lines,
                1,
            ),
            hide_index=True,
            use_container_width=True,
        )

    st.caption(
        "Inverse historical frequencies "
        "only. Not calibrated fair prices "
        "or evidence of betting value."
    )

    # New audit section uses the same
    # historical records as the prices.
    render_audit(
        saved.get("audit", [])
    )


# ==========================================
# HISTORICAL TEAM MATCHING
# ==========================================

def exact_match(api_name, find_team_names):
    matches = find_team_names(
        api_name[:5]
    )

    exact = next(
        (
            name
            for name in matches
            if name.casefold()
            == api_name.casefold()
        ),
        None,
    )

    return exact, matches


# ==========================================
# LIVE FIXTURES PAGE
# ==========================================

def render_live_fixtures(
    leagues,
    find_team_names,
    show_comparison,
):
    st.header("⚽ Live Fixtures")

    st.caption(
        "Select a fixture to inspect "
        "its statistics, halftime markets "
        "and historical match audit."
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
        match_payload.clear()

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

    selected_leagues = {
        str(code)
        for code in chosen
    }

    for item in found:
        start = kickoff(item)

        if (
            str(item.get("competition_id"))
            in selected_leagues
            and start is not None
            and start.date() == day
            and item.get("id")
        ):
            by_id[str(item["id"])] = item

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
            "No matches found for this date "
            "in the selected leagues."
        )
        return

    selected_id = st.selectbox(
        "Select a match",
        list(by_id),
        index=None,
        placeholder="Choose a fixture to view its current match state",
        format_func=lambda mid: (
            fixture_label(by_id[mid])
        ),
        key="lf_match_id",
    )

    if selected_id is None:
        st.info("Select a fixture above to load its current statistics and halftime pricing.")
        return

    selected = by_id[selected_id]

    home_api = team_name(
        selected,
        "home",
    )

    away_api = team_name(
        selected,
        "away",
    )

    st.subheader(
        f"{home_api} v {away_api}"
    )

    league_name = next(
        (
            name
            for code, name in leagues.items()
            if str(code)
            == str(
                selected.get("competition_id")
            )
        ),
        "League",
    )

    st.caption(league_name)

    # ======================================
    # FETCH DETAILS AND STATISTICS
    # ======================================

    try:
        with st.spinner(
            "Retrieving match information..."
        ):
            details_response = match_payload(
                key,
                selected_id,
                "details",
            )

            details = (
                details_response["data"]
                or selected
            )

            live_response = match_payload(
                key,
                selected_id,
                "live",
            )

            live_stats = live_response["data"]

            historical_response = None

            if not isinstance(live_stats, dict):
                historical_response = (
                    match_payload(
                        key,
                        selected_id,
                        "historical",
                    )
                )

            snapshot = (
                live_stats
                if isinstance(live_stats, dict)
                else (
                    historical_response["data"]
                    if historical_response
                    else None
                )
            )

    except requests.RequestException as exc:
        st.warning(
            "Statistics request failed: "
            f"{exc}"
        )

        details = selected
        snapshot = None

        live_response = {
            "status": None
        }

        historical_response = None

    if live_response["status"] == 409:
        st.info(
            "Live statistics returned 409. "
            "Checking historical statistics."
        )

    if (
        historical_response
        and historical_response["status"]
        in (404, 409)
    ):
        st.info(
            "Historical statistics are "
            "not available for this match."
        )

    # ======================================
    # MATCH STATISTICS
    # ======================================

    if isinstance(snapshot, dict):
        meta = snapshot.get("meta") or {}

        st.caption(
            "Feed minute: "
            f"{meta.get('elapsed_minutes', '—')}"
            " · status: "
            f"{selected.get('status', 'unknown')}"
        )

        stats = (
            snapshot.get("stats")
            or snapshot.get("overview")
            or {}
        )

        if isinstance(stats, dict):
            rows = []

            for label, field in (
                ("Shots", "total_shots"),
                (
                    "Shots on target",
                    "shots_on_target",
                ),
                ("Corners", "corner_kicks"),
                (
                    "Yellow cards",
                    "yellow_cards",
                ),
                ("Red cards", "red_cards"),
                ("xG", "expected_goals"),
            ):
                item = stats.get(field) or {}

                values = (
                    pair(item.get("all"))
                    if isinstance(item, dict)
                    else None
                )

                if values is not None:
                    rows.append({
                        "Statistic": label,
                        "Home": values[0],
                        "Away": values[1],
                    })

            if rows:
                st.dataframe(
                    pd.DataFrame(rows),
                    hide_index=True,
                    use_container_width=True,
                )

    # ======================================
    # AUTOMATIC PRICING + AUDIT
    # ======================================

    values = extract_ht(
        details,
        snapshot,
    )

    show_prices(
        values,
        day,
        selected_id,
    )

    # ======================================
    # FEED DIAGNOSTICS
    # ======================================

    with st.expander(
        "🔍 Feed diagnostics and available fields"
    ):
        st.write(
            "Match ID:",
            selected_id,
        )

        st.write(
            "Match status:",
            selected.get("status"),
        )

        st.write(
            "Live endpoint HTTP status:",
            live_response.get("status"),
        )

        if historical_response:
            st.write(
                "Historical endpoint HTTP status:",
                historical_response.get(
                    "status"
                ),
            )

        st.markdown(
            "#### Actual match score object"
        )

        st.json(
            details.get("score")
            if isinstance(details, dict)
            else None
        )

        st.markdown(
            "#### Fixture-list score object"
        )

        st.json(
            selected.get("score")
        )

        st.markdown(
            "#### Statistics metadata"
        )

        st.json(
            (snapshot.get("meta") or {})
            if isinstance(snapshot, dict)
            else {}
        )

        st.write(
            "Match detail keys:",
            (
                list(details)
                if isinstance(details, dict)
                else []
            ),
        )

        st.write(
            "Statistics keys:",
            (
                list(snapshot)
                if isinstance(snapshot, dict)
                else []
            ),
        )

        st.write(
            "Available first-half fields:",
            {
                name: value is not None
                for name, value in values.items()
            },
        )

        st.caption(
            "Diagnostic fields do not "
            "display the API key."
        )

    # ======================================
    # HISTORICAL TEAM COMPARISON
    # ======================================

    st.divider()

    st.header(
        "Historical comparison "
        "and potential angles"
    )

    try:
        home, home_options = exact_match(
            home_api,
            find_team_names,
        )

        away, away_options = exact_match(
            away_api,
            find_team_names,
        )

    except Exception as exc:
        st.error(
            "Historical team lookup failed: "
            f"{type(exc).__name__}: {exc}"
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
        selected_id,
        home,
        away,
        home_count,
        away_count,
    )

    if st.button(
        "📊 Analyse this fixture",
        use_container_width=True,
        disabled=not (
            home
            and away
            and home != away
        ),
        key="lf_analyse",
    ):
        st.session_state[
            "lf_selection"
        ] = selection

    if (
        st.session_state.get("lf_selection")
        == selection
    ):
        try:
            show_comparison(
                home,
                away,
                home_count,
                away_count,
                20,
                (
                    day - timedelta(days=1)
                ).isoformat(),
            )

        except Exception as exc:
            st.error(
                "Historical analysis failed: "
                f"{type(exc).__name__}: {exc}"
            )
