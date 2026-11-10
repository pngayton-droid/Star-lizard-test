
import math
from datetime import date
import streamlit as st

PAGE_SIZE = 100
MAX_CANDIDATES = 3000
MIN_SAMPLE = 30


def number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def integer(value):
    result = number(value)
    if result is None or result < 0 or not result.is_integer():
        return None
    return int(result)


def extract_market(stats, key):
    try:
        periods = stats["overview"][key]
        result = {}

        for period in ("first_half", "second_half", "all"):
            home = integer(periods[period]["home"])
            away = integer(periods[period]["away"])

            if home is None or away is None:
                return None

            result[period] = (home, away)

        for side in (0, 1):
            if (
                result["first_half"][side]
                + result["second_half"][side]
                != result["all"][side]
            ):
                return None

        return result

    except (KeyError, TypeError, AttributeError, IndexError):
        return None


def candidates_query(db, hh, ah, hx, ax, tol, cutoff):
    rows = []
    offset = 0

    while len(rows) < MAX_CANDIDATES:
        size = min(
            PAGE_SIZE,
            MAX_CANDIDATES - len(rows),
        )

        response = (
            db.table("historical_xg")
            .select(
                "match_id,match_date,"
                "home_ht_goals,away_ht_goals,"
                "home_ht_xg,away_ht_xg"
            )
            .eq("home_ht_goals", hh)
            .eq("away_ht_goals", ah)
            .gte("home_ht_xg", max(0.0, hx - tol))
            .lte("home_ht_xg", hx + tol)
            .gte("away_ht_xg", max(0.0, ax - tol))
            .lte("away_ht_xg", ax + tol)
            .lt("match_date", cutoff)
            .order("match_date", desc=True)
            .order("match_id")
            .range(offset, offset + size - 1)
            .execute()
        )

        batch = response.data or []

        if not batch:
            break

        rows.extend(batch)
        offset += len(batch)

        if len(batch) < size:
            break

    unique = {}

    for row in rows:
        match_id = row.get("match_id")

        if match_id is not None:
            unique[str(match_id)] = row

    return unique, len(rows) == MAX_CANDIDATES


def collect(
    db,
    candidates,
    corner_home,
    corner_away,
    corner_tol,
    yellow_home,
    yellow_away,
    yellow_tol,
    team_split,
):
    records = {
        "corners": [],
        "yellows": [],
    }

    ids = list(candidates)
    event_count = 0

    for start in range(0, len(ids), PAGE_SIZE):
        batch_ids = ids[start:start + PAGE_SIZE]

        response = (
            db.table("historical_match_events")
            .select("match_id,stats_data")
            .in_("match_id", batch_ids)
            .execute()
        )

        event_rows = response.data or []
        event_count += len(event_rows)

        for row in event_rows:
            if str(row.get("match_id")) not in candidates:
                continue

            stats = row.get("stats_data")

            if not isinstance(stats, dict):
                continue

            for label, key, home, away, tolerance in (
                (
                    "corners",
                    "corner_kicks",
                    corner_home,
                    corner_away,
                    corner_tol,
                ),
                (
                    "yellows",
                    "yellow_cards",
                    yellow_home,
                    yellow_away,
                    yellow_tol,
                ),
            ):
                result = extract_market(stats, key)

                if result is None:
                    continue

                first_home, first_away = result["first_half"]

                if team_split:
                    qualifies = (
                        abs(first_home - home) <= tolerance
                        and abs(first_away - away) <= tolerance
                    )
                else:
                    qualifies = (
                        abs(
                            (first_home + first_away)
                            - (home + away)
                        )
                        <= tolerance
                    )

                if qualifies:
                    second_home, second_away = result["second_half"]
                    all_home, all_away = result["all"]

                    records[label].append((
                        second_home + second_away,
                        all_home + all_away,
                        second_home,
                        second_away,
                        all_home,
                        all_away,
                    ))

        del event_rows

    return records, event_count


def market_table(records, lines, index):
    n = len(records)
    output = []

    for line in lines:
        hits = sum(
            item[index] > line
            for item in records
        )

        probability = hits / n if n else 0.0

        output.append({
            "Market": f"Over {line:.1f}",
            "Hits": f"{hits}/{n}",
            "Rate": (
                f"{probability:.1%}"
                if n >= MIN_SAMPLE
                else "—"
            ),
            "Inverse rate": (
                f"{1 / probability:.2f}"
                if n >= MIN_SAMPLE and hits
                else "—"
            ),
        })

    return output


def display_section(
    title,
    records,
    lines_second,
    lines_full,
):
    st.subheader(title)

    n = len(records)

    st.caption(
        f"{n} validated matching records"
    )

    if n < MIN_SAMPLE:
        st.warning(
            f"Only {n} comparable records. "
            f"Minimum {MIN_SAMPLE}; prices withheld."
        )
        return

    st.markdown("**Second-half match totals**")

    st.dataframe(
        market_table(records, lines_second, 0),
        hide_index=True,
        use_container_width=True,
    )

    st.markdown("**Full-match totals**")

    st.dataframe(
        market_table(records, lines_full, 1),
        hide_index=True,
        use_container_width=True,
    )

    with st.expander(
        "Home and away second-half breakdown"
    ):
        left, right = st.columns(2)

        with left:
            st.markdown("**Home team**")

            st.dataframe(
                market_table(records, lines_second, 2),
                hide_index=True,
                use_container_width=True,
            )

        with right:
            st.markdown("**Away team**")

            st.dataframe(
                market_table(records, lines_second, 3),
                hide_index=True,
                use_container_width=True,
            )


def render_halftime_markets(db):
    st.header(
        "🦎 V5.7 Halftime Corners & Cards"
    )

    st.caption(
        "Read-only, bounded historical comparison. "
        "No full-history memory cache."
    )

    with st.form("v57_market_form"):
        left, right = st.columns(2)

        with left:
            hh = st.number_input(
                "Home HT goals",
                min_value=0,
                max_value=15,
                value=0,
            )

            hx = st.number_input(
                "Home HT xG",
                min_value=0.0,
                max_value=10.0,
                value=0.85,
                step=0.05,
            )

            hc = st.number_input(
                "Home HT corners",
                min_value=0,
                max_value=30,
                value=3,
            )

            hy = st.number_input(
                "Home HT yellows",
                min_value=0,
                max_value=20,
                value=1,
            )

        with right:
            ah = st.number_input(
                "Away HT goals",
                min_value=0,
                max_value=15,
                value=1,
            )

            ax = st.number_input(
                "Away HT xG",
                min_value=0.0,
                max_value=10.0,
                value=0.35,
                step=0.05,
            )

            ac = st.number_input(
                "Away HT corners",
                min_value=0,
                max_value=30,
                value=2,
            )

            ay = st.number_input(
                "Away HT yellows",
                min_value=0,
                max_value=20,
                value=2,
            )

        with st.expander("Matching settings"):
            xt = st.slider(
                "HT xG tolerance",
                0.10,
                1.00,
                0.30,
                0.05,
            )

            ct = st.slider(
                "HT corner tolerance",
                0,
                5,
                2,
            )

            yt = st.slider(
                "HT yellow tolerance",
                0,
                4,
                1,
            )

            team_split = st.checkbox(
                "Match home and away HT "
                "corners/cards separately",
                value=False,
            )

            cutoff = st.date_input(
                "Fixture date "
                "(exclude this date and later)",
                value=date.today(),
                max_value=date.today(),
            )

        submitted = st.form_submit_button(
            "Calculate historical market rates",
            type="primary",
            use_container_width=True,
        )

    if not submitted:
        st.info(
            "Set the halftime observations and "
            "tap Calculate. No event data is "
            "loaded until then."
        )
        return

    try:
        with st.spinner(
            "Retrieving and validating "
            "comparable historical matches..."
        ):
            candidates, capped = candidates_query(
                db,
                int(hh),
                int(ah),
                float(hx),
                float(ax),
                float(xt),
                cutoff.isoformat(),
            )

            records, fetched = collect(
                db,
                candidates,
                int(hc),
                int(ac),
                int(ct),
                int(hy),
                int(ay),
                int(yt),
                team_split,
            )

    except Exception as exc:
        st.error(
            f"Lookup failed: "
            f"{type(exc).__name__}: {exc}"
        )
        return

    st.caption(
        f"{len(candidates)} distinct HT score/xG "
        f"candidates; {fetched} event rows returned."
    )

    if capped:
        st.warning(
            "3,000-row safety cap reached. "
            "This is a recent-match subset, "
            "not the entire historical population."
        )

    st.caption(
        "HT corners/cards matched "
        + (
            "by individual home and away counts."
            if team_split
            else "by combined match totals."
        )
    )

    display_section(
        "🚩 Corners",
        records["corners"],
        [3.5, 4.5, 5.5, 6.5],
        [7.5, 8.5, 9.5, 10.5, 11.5],
    )

    display_section(
        "🟨 Yellow cards",
        records["yellows"],
        [1.5, 2.5, 3.5, 4.5],
        [3.5, 4.5, 5.5, 6.5],
    )

    st.caption(
        "Historical rates and their reciprocals "
        "are not calibrated fair odds, verified "
        "live prices, or proof of betting value. "
        "Yellow cards are counts, not bookmaker "
        "card points."
    )
