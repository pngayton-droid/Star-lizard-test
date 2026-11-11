"""Experimental, uncalibrated xG Poisson pricing. No bookmaker data used."""
from math import exp, factorial


def estimate(home_df, away_df, prior=1.35, strength=8):
    """Shrink venue attack/defence xG towards a neutral prior."""
    def mean_n(df, field):
        values = []
        for value in df[field].tolist():
            try:
                x = float(value)
                if x >= 0 and x < 12:
                    values.append(x)
            except (TypeError, ValueError):
                pass
        return (sum(values) / len(values), len(values)) if values else (None, 0)

    if home_df.empty or away_df.empty:
        return None
    components = [
        mean_n(home_df, "xGF"),
        mean_n(away_df, "xGA"),
        mean_n(away_df, "xGF"),
        mean_n(home_df, "xGA"),
    ]
    if any(n < 5 for _, n in components):
        return None
    shrunk = [(avg * n + prior * strength) / (n + strength)
              for avg, n in components]
    home_rate = max(0.15, min(4.0, (shrunk[0] + shrunk[1]) / 2))
    away_rate = max(0.15, min(4.0, (shrunk[2] + shrunk[3]) / 2))
    return home_rate, away_rate, [n for _, n in components]


def probabilities(home_rate, away_rate):
    """Independent Poisson goal counts; finite tail included at 12 goals."""
    def pmf(rate):
        values = [exp(-rate) * rate ** k / factorial(k) for k in range(12)]
        values.append(max(0.0, 1.0 - sum(values)))
        return values

    h, a = pmf(home_rate), pmf(away_rate)
    markets = {
        "Home win": 0.0, "Draw": 0.0, "Away win": 0.0,
        "Home or draw": 0.0, "Away or draw": 0.0,
        "Home team to score": 1 - h[0],
        "Away team to score": 1 - a[0],
        "BTTS Yes": (1 - h[0]) * (1 - a[0]),
    }
    for i, hp in enumerate(h):
        for j, ap in enumerate(a):
            p = hp * ap
            if i > j:
                markets["Home win"] += p
            elif i == j:
                markets["Draw"] += p
            else:
                markets["Away win"] += p
    markets["Home or draw"] = markets["Home win"] + markets["Draw"]
    markets["Away or draw"] = markets["Away win"] + markets["Draw"]
    markets["BTTS No"] = 1 - markets["BTTS Yes"]
    for threshold in (1.5, 2.5, 3.5):
        markets[f"Over {threshold} goals"] = sum(
            hp * ap for i, hp in enumerate(h)
            for j, ap in enumerate(a) if i + j > threshold
        )
    return markets
