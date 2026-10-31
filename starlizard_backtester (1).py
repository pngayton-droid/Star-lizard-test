"""Starlizard: standalone walk-forward pre-match Poisson evaluation.

No Streamlit/API/GitHub writes. Uses the existing model.py and football-data-style
CSV. Odds are historical research snapshots, not verified executable quotes.
"""
import argparse
import numpy as np
import pandas as pd
from model import Model, load

OUTCOMES = ('home', 'draw', 'away')
ODDS_SETS = [('B365CH','B365CD','B365CA'), ('PSCH','PSCD','PSCA'),
             ('B365H','B365D','B365A'), ('PSH','PSD','PSA'),
             ('AvgCH','AvgCD','AvgCA'), ('AvgH','AvgD','AvgA')]


def _odds_columns(df, requested='auto'):
    available = [cols for cols in ODDS_SETS if all(c in df.columns for c in cols)]
    if requested != 'auto':
        cols = tuple(requested.split(','))
        if len(cols) != 3 or not all(c in df.columns for c in cols):
            raise ValueError('Requested odds columns must be three existing CSV columns, e.g. B365CH,B365CD,B365CA')
        return cols
    return available[0] if available else None


def _scores(frame, prefix):
    if frame.empty:
        return {'brier': None, 'log_loss': None}
    p = frame[[prefix + x for x in OUTCOMES]].to_numpy(dtype=float)
    y = np.array([OUTCOMES.index(x) for x in frame.outcome], dtype=int)
    return {'brier': float(np.mean(np.sum((p - np.eye(3)[y])**2, axis=1))),
            'log_loss': float(-np.mean(np.log(np.maximum(p[np.arange(len(y)), y], 1e-12))))}


def backtest(path, cutoff='2024-08-01', odds_columns='auto', min_edge=0.05):
    if min_edge < 0:
        raise ValueError('min_edge must be nonnegative')
    df = load(path)
    # Same fixture must not enter the rolling model twice.
    df = df.drop_duplicates(subset=['date', 'Div', 'HomeTeam', 'AwayTeam'], keep='first')
    cols = _odds_columns(df, odds_columns)
    if cols:
        for col in cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    model = Model()
    records = []
    start = pd.Timestamp(cutoff)
    for date, day in df.groupby('date', sort=True):
        pending = []
        for r in day.to_dict('records'):
            league, home, away = str(r['Div']), str(r['HomeTeam']), str(r['AwayTeam'])
            gh, ga = int(r['FTHG']), int(r['FTAG'])
            prediction = model.predict(league, home, away)
            if date >= start and prediction is not None:
                lh, la, probs = prediction
                actual = 'home' if gh > ga else 'draw' if gh == ga else 'away'
                row = {'date': date.date().isoformat(), 'league': league,
                       'home_team': home, 'away_team': away, 'home_goals': gh,
                       'away_goals': ga, 'outcome': actual,
                       'lambda_home': lh, 'lambda_away': la}
                for k in OUTCOMES:
                    row['model_' + k] = probs[k]
                if cols:
                    prices = np.array([r.get(c) for c in cols], dtype=float)
                    if np.isfinite(prices).all() and (prices > 1).all():
                        inverse = 1 / prices
                        market = inverse / inverse.sum()  # proportional margin removal
                        for i, k in enumerate(OUTCOMES):
                            row['odds_' + k] = prices[i]
                            row['market_' + k] = market[i]
                            row['ev_' + k] = probs[k] * prices[i] - 1
                        row['overround'] = inverse.sum() - 1
                        # One selection at most per match; highest estimated EV wins.
                        best = max(OUTCOMES, key=lambda k: row['ev_' + k])
                        if row['ev_' + best] >= min_edge:
                            row['bet'] = best
                            row['bet_odds'] = row['odds_' + best]
                            row['profit_1unit'] = row['bet_odds'] - 1 if best == actual else -1.0
                records.append(row)
            pending.append((league, home, away, gh, ga))
        # All fixtures on the same calendar date are predicted before updates.
        for item in pending:
            model.update(*item)
    results = pd.DataFrame(records)
    summary = {'cutoff': str(start.date()), 'total_predictions': len(results),
               'odds_columns': list(cols) if cols else None,
               'minimum_model_ev': min_edge,
               'model': _scores(results, 'model_') if len(results) else None}
    if len(results) and cols:
        priced = results.dropna(subset=['market_' + x for x in OUTCOMES])
        summary['priced_matches'] = len(priced)
        summary['model_on_priced'] = _scores(priced, 'model_')
        summary['market_on_priced'] = _scores(priced, 'market_')
        bets = priced.dropna(subset=['bet']) if 'bet' in priced else priced.iloc[0:0]
        profit = float(bets.profit_1unit.sum()) if len(bets) else 0.0
        summary['bets'] = len(bets)
        summary['profit_units'] = profit
        summary['roi'] = profit / len(bets) if len(bets) else None
        summary['bet_win_rate'] = float((bets.bet == bets.outcome).mean()) if len(bets) else None
    else:
        summary['priced_matches'] = 0
        summary['warning'] = 'No compatible complete 1X2 bookmaker odds columns found.' if not cols else 'No eligible model predictions.'
    return results, summary


def main():
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', required=True)
    parser.add_argument('--cutoff', default='2024-08-01')
    parser.add_argument('--odds-columns', default='auto', help='auto or comma-separated home,draw,away columns')
    parser.add_argument('--min-edge', type=float, default=0.05, help='minimum estimated ROI, e.g. 0.05')
    parser.add_argument('--out', default='starlizard_walkforward_results.csv')
    args = parser.parse_args()
    results, summary = backtest(args.csv, args.cutoff, args.odds_columns, args.min_edge)
    results.to_csv(args.out, index=False)
    print(json.dumps(summary, indent=2))
    print('Research only: historical odds timing and bet availability are not independently verified.')


if __name__ == '__main__':
    main()
