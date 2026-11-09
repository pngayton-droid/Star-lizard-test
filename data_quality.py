
"""
PRO STARLIZARD - Historical Data Quality

Reusable, read-only eligibility rules for modelling.

Does not alter Supabase records or verification flags.
"""

import pandas as pd

# Excluded from model training until sufficient history exists.
EXCLUDED_COMPETITIONS = {"comp_6387"}

MARKETS = {
    "corners": ("corner_kicks", "corners_match"),
    "yellow_cards": ("yellow_cards", "yellow_cards_match"),
    "red_cards": ("red_cards", "red_cards_match"),
}


def _get(data, *keys):
    """Safely retrieve a nested value from a dictionary."""
    for key in keys:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def _number(value):
    """Accept valid numeric statistics, including zero."""
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
        if not pd.notna(result):
            return None
        return result
    except (TypeError, ValueError):
        return None


def _flag_is_true(value):
    """Handle Supabase booleans and string representations."""
    return value is True or (
        isinstance(value, str)
        and value.strip().lower() == "true"
    )


def _consistent_halves(stats, field):
    """
    Check both teams' full-match totals against their
    first-half and second-half statistics.
    """
    for team in ("home", "away"):
        total = _number(
            _get(stats, "overview", field, "all", team)
        )
        first = _number(
            _get(stats, "overview", field, "first_half", team)
        )
        second = _number(
            _get(stats, "overview", field, "second_half", team)
        )

        if None in (total, first, second):
            return False

        if abs(total - first - second) > 0.000001:
            return False

    return True


def classify_match(record, market="corners"):
    """
    Classify one match for a particular market.

    Returns:
      excluded_competition
      timeline_verified
      partial_totals_only
      excluded_unverified

    A partial timeline never qualifies for event-timing work.
    """
    if market not in MARKETS:
        raise ValueError(f"Unsupported market: {market}")

    if record.get("competition_id") in EXCLUDED_COMPETITIONS:
        return "excluded_competition"

    field, flag = MARKETS[market]

    stats = record.get("stats_data")
    timeline = record.get("timeline_data")

    # Never accept a verified flag without actual totals.
    totals_present = all(
        _number(_get(stats, "overview", field, "all", team))
        is not None
        for team in ("home", "away")
    )

    if not totals_present:
        return "excluded_unverified"

    coverage = _get(timeline, "coverage")

    # Preserve existing full-timeline verification.
    if coverage == "full" and _flag_is_true(
        record.get(flag)
    ):
        return "timeline_verified"

    # Partial timelines may support totals, but not timing.
    if coverage == "partial" and _consistent_halves(
        stats, field
    ):
        return "partial_totals_only"

    return "excluded_unverified"


def eligible_for_totals(record, market="corners"):
    """Whether a match may train a totals model."""
    return classify_match(record, market) in {
        "timeline_verified",
        "partial_totals_only",
    }


def eligible_for_timing(record, market="corners"):
    """Only fully verified timelines support timing research."""
    return classify_match(record, market) == (
        "timeline_verified"
    )


def add_quality_columns(df, markets=("corners", "yellow_cards")):
    """
    Add eligibility columns without modifying the input DataFrame.

    Requires:
      competition_id, stats_data, timeline_data,
      and the relevant verification flags.
    """
    result = df.copy()

    for market in markets:
        if market not in MARKETS:
            raise ValueError(f"Unsupported market: {market}")

        column = f"{market}_quality"

        result[column] = result.apply(
            lambda row: classify_match(
                row.to_dict(), market
            ),
            axis=1,
        )

        result[f"{market}_totals_usable"] = (
            result[column].isin(
                ["timeline_verified", "partial_totals_only"]
            )
        )

        result[f"{market}_timing_usable"] = (
            result[column] == "timeline_verified"
        )

    return result


def quality_summary(df, market="corners"):
    """Summarise match classifications by competition."""
    checked = add_quality_columns(df, markets=(market,))

    return (
        checked.groupby(
            ["competition_id", f"{market}_quality"],
            dropna=False,
        )
        .size()
        .unstack(fill_value=0)
    )
