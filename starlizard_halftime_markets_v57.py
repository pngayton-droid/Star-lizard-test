
"""
PRO STARLIZARD V5.7
Halftime Pricing Terminal + Historical Match Audit

Read-only Supabase research.

Preserves:
- Existing matching rules
- Existing pricing calculations
- Existing collect() return format by default
- Mobile historical pricing interface

Adds:
- Individual historical match audit
- First-half, second-half and full-time totals
- Reconciliation checks
- CSV export
"""

import math
from datetime import date

import pandas as pd
import streamlit as st


PAGE_SIZE = 100
MAX_CANDIDATES = 3000
MIN_SAMPLE = 30

RESULTS_KEY = "v57_compact_results"


# ==========================================
# VALIDATION
# ==========================================

def number(value):
    if isinstance(value, bool):
        return None

    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def integer(value):
    value = number(value)

    if (
        value is None
        or value < 0
        or not value.is_integer()
    ):
        return None

    return int(value)


def extract_market(stats, key):
    try:
        periods = stats["overview"][key]
        result = {}

        for period in (
            "first_half",
            "second_half",
            "all",
        ):
            home = integer(
                periods[period]["home"]
            )
            away = integer(
                periods[period]["away"]
            )

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

    except (
        KeyError,
        TypeError,
        AttributeError,
        IndexError,
    ):
        return None


# ==========================================
# HISTORICAL CANDIDATES
# ==========================================

def candidates_query(
    db,
    hh,
    ah,
    hx,
    ax,
    tolerance,
    cutoff,
):
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
            .gte(
                "home_ht_xg",
                max(0.0, hx - tolerance),
            )
            .lte("home_ht_xg", hx + tolerance)
            .gte(
                "away_ht_xg",
                max(0.0, ax - tolerance),
            )
            .lte("away_ht_xg", ax + tolerance)
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

    return unique, len(rows) >= MAX_CANDIDATES


# ==========================================
# HISTORICAL EVENT COLLECTION
# ==========================================

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
    return_audit=False,
    return_baseline=False,
):
    """
    Default return remains:
        records, event_count

    Optional audit return:
        records, event_count, audit_rows

    This keeps existing Live Fixtures
    callers compatible.
    """

    records = {
        "corners": [],
        "yellows": [],
    }

    audit_rows = []
    baseline = {"corners": [], "yellows": []}
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
            match_id = str(row.get("match_id"))

            if match_id not in candidates:
                continue

            stats = row.get("stats_data")

            if not isinstance(stats, dict):
                continue

            candidate = candidates[match_id]

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

                fh, fa = result["first_half"]
                sh, sa = result["second_half"]
                ah, aa = result["all"]
                if return_baseline:
                    baseline[label].append((sh + sa, ah + aa, sh, sa, ah, aa))

                if team_split:
                    qualifies = (
                        abs(fh - home) <= tolerance
                        and abs(fa - away) <= tolerance
                    )
                else:
                    qualifies = (
                        abs((fh + fa) - (home + away))
                        <= tolerance
                    )

                if not qualifies:
                    continue

                # Preserve the exact six-value
                # format used by pricing.
                records[label].append((
                    sh + sa,
                    ah + aa,
                    sh,
                    sa,
                    ah,
                    aa,
                ))

                if return_audit:
                    audit_rows.append({
                        "Market": label,
                        "Match ID": match_id,
                        "Date": candidate.get(
                            "match_date"
                        ),
                        "HT score": (
                            f"{candidate.get('home_ht_goals')}"
                            "-"
                            f"{candidate.get('away_ht_goals')}"
                        ),
                        "Home HT xG": candidate.get(
                            "home_ht_xg"
                        ),
                        "Away HT xG": candidate.get(
                            "away_ht_xg"
                        ),
                        "1H home": fh,
                        "1H away": fa,
                        "1H total": fh + fa,
                        "2H home": sh,
                        "2H away": sa,
                        "2H total": sh + sa,
                        "FT home": ah,
                        "FT away": aa,
                        "FT total": ah + aa,
                        "Reconciled": (
                            fh + sh == ah
                            and fa + sa == aa
                        ),
                    })

        del event_rows

    if return_audit and return_baseline:
        return records, event_count, audit_rows, baseline
    if return_audit:
        return records, event_count, audit_rows
    if return_baseline:
        return records, event_count, baseline
    return records, event_count


# ==========================================
# PRICING TABLES
# ==========================================

def market_table(records, lines, index):
    sample = len(records)
    output = []

    for line in lines:
        hits = sum(
            item[index] > line
            for item in records
        )

        if sample >= MIN_SAMPLE:
            probability = hits / sample
            rate = f"{probability:.1%}"

            inverse = (
                f"{1 / probability:.2f}"
                if probability > 0
                else "—"
            )
        else:
            rate = "—"
            inverse = "—"

        output.append({
            "Market": f"O {line:.1f}",
            "Hits": f"{hits}/{sample}",
            "Rate": rate,
            "Odds*": inverse,
        })

    return pd.DataFrame(output)


def pricing_snapshot(records, lines, index, label):
    """Display one illustrative historical line without implying market value."""
    sample = len(records)
    if sample < MIN_SAMPLE:
        st.metric(label + " · sample", str(sample))
        st.caption("At least 30 comparable records required.")
        return
    line = lines[0]
    hits = sum(row[index] > line for row in records)
    rate = hits / sample
    odds = f"{1 / rate:.2f}" if rate else "—"
    st.metric(label + f" · Over {line:.1f}", f"{rate:.1%}")
    st.caption(f"{hits}/{sample} matches · inverse historical odds {odds}")


def compact_table(records, lines, index):
    frame = market_table(
        records,
        lines,
        index,
    )

    st.dataframe(
        frame,
        hide_index=True,
        use_container_width=True,
        height=35 * (len(frame) + 1) + 8,
    )


def market_header(title, records):
    sample = len(records)

    st.markdown(f"#### {title}")
    st.caption(
        f"{sample} matching verified records"
    )

    if sample < MIN_SAMPLE:
        st.warning(
            f"Minimum sample is {MIN_SAMPLE}. "
            "Rates and odds are withheld."
        )
        return False

    return True


# ==========================================
# HISTORICAL AUDIT
# ==========================================

def render_audit(audit_rows):
    st.divider()
    st.subheader("🔎 Historical Match Audit")

    st.caption(
        "Individual historical records "
        "behind the pricing calculations."
    )

    if not audit_rows:
        st.info(
            "No qualifying historical records "
            "were available for audit."
        )
        return

    frame = pd.DataFrame(audit_rows)

    market = st.radio(
        "Audit market",
        ["corners", "yellows"],
        format_func=lambda value: (
            "🚩 Corners"
            if value == "corners"
            else "🟨 Yellow cards"
        ),
        horizontal=True,
        key="v57_audit_market",
    )

    selected = frame[
        frame["Market"] == market
    ].copy()

    st.caption(
        f"{len(selected)} individual "
        "matching records"
    )

    if selected.empty:
        st.info(
            "No records matched this market."
        )
        return

    # Every record used for pricing
    # must appear in the audit.
    failures = selected[
        selected["Reconciled"] == False
    ]

    if failures.empty:
        st.success(
            "All displayed records reconcile: "
            "first half + second half "
            "= full time."
        )
    else:
        st.error(
            f"{len(failures)} records failed "
            "the reconciliation check."
        )

    st.dataframe(
        selected,
        hide_index=True,
        use_container_width=True,
    )

    st.download_button(
        "⬇️ Export audit CSV",
        data=selected.to_csv(
            index=False
        ).encode("utf-8"),
        file_name=(
            f"starlizard_{market}_"
            "historical_audit.csv"
        ),
        mime="text/csv",
        use_container_width=True,
        key="v57_audit_download",
    )

    st.caption(
        "The historical_xg query does not "
        "currently return team names, so "
        "match IDs are shown instead. "
        "No names are guessed."
    )


# ==========================================
# RESULTS
# ==========================================

def render_results():
    result = st.session_state.get(
        RESULTS_KEY
    )

    if not result:
        return

    records = result["records"]

    st.divider()
    st.subheader(
        "Historical Pricing Terminal"
    )

    st.caption(
        f"{result['candidates']} "
        "score/xG candidates · "
        f"{result['fetched']} "
        "event records returned"
    )

    if result["capped"]:
        st.warning(
            "The 3,000-match safety cap "
            "was reached."
        )

    st.caption(
        "Halftime corners/cards matched "
        + (
            "by individual home and away counts."
            if result["team_split"]
            else "by combined match totals."
        )
    )

    view = st.radio(
        "Choose pricing view",
        [
            "Second Half",
            "Full Match",
            "Home / Away",
        ],
        horizontal=True,
        key="v57_result_view",
    )

    corners = records["corners"]
    yellows = records["yellows"]

    st.markdown("#### At a glance")
    a, b = st.columns(2)
    with a:
        pricing_snapshot(corners, [4.5], 0, "2H corners")
    with b:
        pricing_snapshot(yellows, [2.5], 0, "2H yellows")
    st.caption("Illustrative historical frequencies, not calibrated fair odds. No bookmaker quote has been loaded.")

    if view == "Second Half":
        if market_header(
            "🚩 Second-half corners",
            corners,
        ):
            compact_table(
                corners,
                [3.5, 4.5, 5.5, 6.5],
                0,
            )

        if market_header(
            "🟨 Second-half yellow cards",
            yellows,
        ):
            compact_table(
                yellows,
                [1.5, 2.5, 3.5, 4.5],
                0,
            )

    elif view == "Full Match":
        if market_header(
            "🚩 Full-match corners",
            corners,
        ):
            compact_table(
                corners,
                [
                    7.5, 8.5, 9.5,
                    10.5, 11.5,
                ],
                1,
            )

        if market_header(
            "🟨 Full-match yellow cards",
            yellows,
        ):
            compact_table(
                yellows,
                [3.5, 4.5, 5.5, 6.5],
                1,
            )

    else:
        side = st.radio(
            "Historical team",
            ["Home", "Away"],
            horizontal=True,
            key="v57_side_view",
        )

        second_index = (
            2 if side == "Home" else 3
        )
        full_index = (
            4 if side == "Home" else 5
        )

        period = st.radio(
            "Period",
            ["Second Half", "Full Match"],
            horizontal=True,
            key="v57_side_period",
        )

        if period == "Second Half":
            if market_header(
                f"🚩 {side} second-half corners",
                corners,
            ):
                compact_table(
                    corners,
                    [0.5, 1.5, 2.5, 3.5, 4.5],
                    second_index,
                )

            if market_header(
                f"🟨 {side} second-half yellows",
                yellows,
            ):
                compact_table(
                    yellows,
                    [0.5, 1.5, 2.5, 3.5],
                    second_index,
                )

        else:
            if market_header(
                f"🚩 {side} full-match corners",
                corners,
            ):
                compact_table(
                    corners,
                    [1.5, 2.5, 3.5, 4.5, 5.5],
                    full_index,
                )

            if market_header(
                f"🟨 {side} full-match yellows",
                yellows,
            ):
                compact_table(
                    yellows,
                    [0.5, 1.5, 2.5, 3.5, 4.5],
                    full_index,
                )

    st.caption(
        "*Odds are inverse historical "
        "frequencies, not calibrated fair "
        "prices or validated betting edges."
    )

    st.caption(
        "Home/Away refers to sides in "
        "historical matches, not the "
        "specific selected clubs. "
        "Yellow cards are counts, "
        "not bookmaker card points."
    )

    render_audit(
        result.get("audit", [])
    )


# ==========================================
# MANUAL HALFTIME TERMINAL
# ==========================================

def render_halftime_markets(db):
    st.markdown(
        "### 🦎 Halftime Pricing"
    )

    st.caption(
        "Historical corners and cards "
        "pricing · Mobile terminal"
    )

    with st.form("v57_compact_form"):
        st.markdown(
            "**Halftime match state**"
        )

        left, right = st.columns(2)

        with left:
            st.markdown("**HOME**")

            hh = st.number_input(
                "HT goals",
                min_value=0,
                max_value=15,
                value=0,
                key="v57_home_goals",
            )

            hx = st.number_input(
                "HT xG",
                min_value=0.0,
                max_value=10.0,
                value=0.85,
                step=0.05,
                key="v57_home_xg",
            )

            hc = st.number_input(
                "HT corners",
                min_value=0,
                max_value=30,
                value=3,
                key="v57_home_corners",
            )

            hy = st.number_input(
                "HT yellow cards",
                min_value=0,
                max_value=20,
                value=1,
                key="v57_home_yellows",
            )

        with right:
            st.markdown("**AWAY**")

            ah = st.number_input(
                "HT goals",
                min_value=0,
                max_value=15,
                value=1,
                key="v57_away_goals",
            )

            ax = st.number_input(
                "HT xG",
                min_value=0.0,
                max_value=10.0,
                value=0.35,
                step=0.05,
                key="v57_away_xg",
            )

            ac = st.number_input(
                "HT corners",
                min_value=0,
                max_value=30,
                value=2,
                key="v57_away_corners",
            )

            ay = st.number_input(
                "HT yellow cards",
                min_value=0,
                max_value=20,
                value=2,
                key="v57_away_yellows",
            )

        with st.expander(
            "⚙️ Matching settings"
        ):
            xt = st.slider(
                "HT xG tolerance",
                min_value=0.10,
                max_value=1.00,
                value=0.30,
                step=0.05,
                key="v57_xg_tolerance",
            )

            ct = st.slider(
                "HT corner tolerance",
                min_value=0,
                max_value=5,
                value=2,
                key="v57_corner_tolerance",
            )

            yt = st.slider(
                "HT yellow tolerance",
                min_value=0,
                max_value=4,
                value=1,
                key="v57_yellow_tolerance",
            )

            team_split = st.checkbox(
                "Match home and away "
                "HT corners/cards separately",
                value=False,
                key="v57_team_split",
            )

            cutoff = st.date_input(
                "Fixture date",
                value=date.today(),
                max_value=date.today(),
                key="v57_cutoff_date",
            )

        submitted = st.form_submit_button(
            "Calculate Historical Prices",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        st.session_state.pop(
            RESULTS_KEY,
            None,
        )

        try:
            with st.spinner(
                "Analysing comparable "
                "historical matches..."
            ):
                candidates, capped = (
                    candidates_query(
                        db,
                        int(hh),
                        int(ah),
                        float(hx),
                        float(ax),
                        float(xt),
                        cutoff.isoformat(),
                    )
                )

                records, fetched, audit = collect(
                    db,
                    candidates,
                    int(hc),
                    int(ac),
                    int(ct),
                    int(hy),
                    int(ay),
                    int(yt),
                    bool(team_split),
                    return_audit=True,
                )

            st.session_state[
                RESULTS_KEY
            ] = {
                "records": records,
                "audit": audit,
                "candidates": len(candidates),
                "fetched": fetched,
                "capped": capped,
                "team_split": bool(team_split),
            }

        except Exception as exc:
            st.error(
                "Historical calculation failed: "
                f"{type(exc).__name__}: {exc}"
            )
            return

    if st.session_state.get(
        RESULTS_KEY
    ) is not None:
        render_results()
    else:
        st.info(
            "Enter halftime observations "
            "and press Calculate."
        )
