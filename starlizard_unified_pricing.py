
"""
PRO STARLIZARD — Unified Historical Pricing Engine V1

Read-only Supabase historical pricing foundation.

Markets:
- Second-half goals
- Second-half corners
- Second-half yellow cards
- Full-match corners and yellow cards

This module does not change the existing pricing engine,
collectors, Supabase records, or API data.

Red cards are retained as a match-quality feature.
Their settlement interpretation is not changed here.
"""

import os
from collections import Counter
from dataclasses import dataclass
from datetime import date

from supabase import create_client


PAGE_SIZE = 500
MIN_SAMPLE = 100


def number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def integer(value):
    value = number(value)
    if value is None or value < 0 or not value.is_integer():
        return None
    return int(value)


def nested(data, *keys):
    try:
        for key in keys:
            data = data[key]
        return data
    except (KeyError, TypeError):
        return None


def load_table(db, table, columns):
    records = []
    offset = 0

    while True:
        response = (
            db.table(table)
            .select(columns)
            .order("match_id")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        batch = response.data or []
        records.extend(batch)

        if len(batch) < PAGE_SIZE:
            break

        offset += PAGE_SIZE

    return records


def extract_market(stats, name):
    result = {}

    for period in ("all", "first_half", "second_half"):
        home = integer(
            nested(stats, "overview", name, period, "home")
        )
        away = integer(
            nested(stats, "overview", name, period, "away")
        )

        result[period] = (
            home + away
            if home is not None and away is not None
            else None
        )

    a = result["all"]
    h1 = result["first_half"]
    h2 = result["second_half"]

    result["valid"] = (
        a is not None
        and h1 is not None
        and h2 is not None
        and a == h1 + h2
    )

    return result


@dataclass
class HistoricalMatch:
    match_id: str
    match_date: str
    competition_id: str
    ht_home: int
    ht_away: int
    ft_home: int
    ft_away: int
    ht_xg_home: float
    ht_xg_away: float
    corners: dict
    yellows: dict
    reds: dict

    @property
    def second_half_goals(self):
        return (
            self.ft_home + self.ft_away
            - self.ht_home - self.ht_away
        )

    @property
    def home_second_half_goals(self):
        return self.ft_home - self.ht_home

    @property
    def away_second_half_goals(self):
        return self.ft_away - self.ht_away


def build_matches(xg_rows, event_rows):
    events = {
        row["match_id"]: row.get("stats_data") or {}
        for row in event_rows
        if row.get("match_id")
    }

    matches = []
    rejected = Counter()

    for row in xg_rows:
        match_id = row.get("match_id")

        if not match_id or match_id not in events:
            rejected["no_matching_events"] += 1
            continue

        scores = [
            integer(row.get(key))
            for key in (
                "home_ht_goals",
                "away_ht_goals",
                "home_goals",
                "away_goals",
            )
        ]

        xgs = [
            number(row.get("home_ht_xg")),
            number(row.get("away_ht_xg")),
        ]

        if None in scores or None in xgs:
            rejected["incomplete_scores_or_xg"] += 1
            continue

        hh, ah, hf, af = scores

        if hf < hh or af < ah or min(xgs) < 0:
            rejected["invalid_score_or_xg"] += 1
            continue

        stats = events[match_id]

        matches.append(
            HistoricalMatch(
                match_id=match_id,
                match_date=str(row.get("match_date") or ""),
                competition_id=str(
                    row.get("competition_id") or ""
                ),
                ht_home=hh,
                ht_away=ah,
                ft_home=hf,
                ft_away=af,
                ht_xg_home=xgs[0],
                ht_xg_away=xgs[1],
                corners=extract_market(stats, "corner_kicks"),
                yellows=extract_market(stats, "yellow_cards"),
                reds=extract_market(stats, "red_cards"),
            )
        )

    return matches, rejected


def fair_price(wins, total):
    if total <= 0 or wins <= 0:
        return None

    probability = wins / total
    return {
        "wins": wins,
        "sample": total,
        "probability": probability,
        "fair_odds": 1 / probability,
    }


def price_market(matches, predicate, minimum=MIN_SAMPLE):
    valid = [m for m in matches if predicate(m) is not None]
    wins = sum(bool(predicate(m)) for m in valid)

    result = fair_price(wins, len(valid))

    if result is None:
        return None

    result["sufficient_sample"] = len(valid) >= minimum
    return result


def comparable_matches(
    matches,
    ht_home,
    ht_away,
    home_xg,
    away_xg,
    tolerance=0.30,
    before_date=None,
    competition_id=None,
):
    return [
        m for m in matches
        if m.ht_home == ht_home
        and m.ht_away == ht_away
        and abs(m.ht_xg_home - home_xg) <= tolerance
        and abs(m.ht_xg_away - away_xg) <= tolerance
        and (
            before_date is None
            or (m.match_date and m.match_date[:10] < before_date)
        )
        and (
            competition_id is None
            or m.competition_id == str(competition_id)
        )
    ]


def over_goals(line):
    return lambda m: m.second_half_goals > line


def home_scores_second_half(m):
    return m.home_second_half_goals > 0


def away_scores_second_half(m):
    return m.away_second_half_goals > 0


def home_wins_second_half(m):
    return m.home_second_half_goals > m.away_second_half_goals


def market_over(attribute, period, line):
    def check(match):
        market = getattr(match, attribute)
        if not market["valid"]:
            return None
        return market[period] > line

    return check


def format_result(label, result):
    if result is None:
        print(f"{label}: no priced observations")
        return

    status = (
        "OK" if result["sufficient_sample"]
        else "SMALL SAMPLE"
    )

    print(
        f"{label}: "
        f"{result['probability']:.1%} | "
        f"fair {result['fair_odds']:.3f} | "
        f"{result['wins']}/{result['sample']} | "
        f"{status}"
    )


def print_quality(matches, rejected):
    print("\nDATA QUALITY")
    print("-" * 65)
    print("Joined, score-valid matches:", len(matches))

    for key, value in rejected.items():
        print(f"Excluded {key}: {value}")

    for name in ("corners", "yellows", "reds"):
        valid = sum(
            getattr(m, name)["valid"] for m in matches
        )
        print(
            f"{name}: {valid} internally consistent "
            f"records out of {len(matches)}"
        )


def main():
    print("PRO STARLIZARD — UNIFIED HISTORICAL PRICING V1")
    print("=" * 65)

    db = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SECRET_KEY"],
    )

    print("Loading historical matches...")

    xg_rows = load_table(
        db,
        "historical_xg",
        "match_id,match_date,competition_id,"
        "home_ht_goals,away_ht_goals,"
        "home_goals,away_goals,"
        "home_ht_xg,away_ht_xg",
    )

    event_rows = load_table(
        db,
        "historical_match_events",
        "match_id,stats_data",
    )

    print("Historical xG records:", len(xg_rows))
    print("Historical event records:", len(event_rows))

    matches, rejected = build_matches(xg_rows, event_rows)

    print_quality(matches, rejected)

    # Test case used in our earlier halftime research.
    # Cutoff prevents future-dated observations.
    sample = comparable_matches(
        matches,
        ht_home=0,
        ht_away=1,
        home_xg=0.85,
        away_xg=0.35,
        tolerance=0.30,
        before_date=date.today().isoformat(),
    )

    print("\nHALFTIME SCENARIO")
    print("-" * 65)
    print("Score: Home 0-1 Away")
    print("Home xG: 0.85")
    print("Away xG: 0.35")
    print("xG tolerance: +/- 0.30")
    print("Comparable historical matches:", len(sample))

    markets = [
        ("Home scores 2H", home_scores_second_half),
        ("Away scores 2H", away_scores_second_half),
        ("Home wins 2H", home_wins_second_half),
        ("Over 0.5 goals 2H", over_goals(0.5)),
        ("Over 1.5 goals 2H", over_goals(1.5)),
        ("Over 2.5 goals 2H", over_goals(2.5)),
        (
            "Over 3.5 corners 2H",
            market_over("corners", "second_half", 3.5),
        ),
        (
            "Over 4.5 corners 2H",
            market_over("corners", "second_half", 4.5),
        ),
        (
            "Over 5.5 corners 2H",
            market_over("corners", "second_half", 5.5),
        ),
        (
            "Over 1.5 yellow cards 2H",
            market_over("yellows", "second_half", 1.5),
        ),
        (
            "Over 2.5 yellow cards 2H",
            market_over("yellows", "second_half", 2.5),
        ),
        (
            "Over 3.5 yellow cards 2H",
            market_over("yellows", "second_half", 3.5),
        ),
        (
            "Over 8.5 corners FT",
            market_over("corners", "all", 8.5),
        ),
        (
            "Over 9.5 corners FT",
            market_over("corners", "all", 9.5),
        ),
        (
            "Over 3.5 yellow cards FT",
            market_over("yellows", "all", 3.5),
        ),
        (
            "Over 4.5 yellow cards FT",
            market_over("yellows", "all", 4.5),
        ),
    ]

    print("\nHISTORICAL FAIR PRICES")
    print("-" * 65)

    for label, predicate in markets:
        format_result(
            label,
            price_market(sample, predicate),
        )

    print("\nNOTES")
    print("Historical frequencies, not calibrated forecasts.")
    print("FT markets shown are conditional on halftime state.")
    print("Yellow cards only; bookmaker card points may differ.")
    print("No data written. Existing engine unchanged.")
    print("\nUNIFIED PRICING V1 COMPLETE")


if __name__ == "__main__":
    main()
