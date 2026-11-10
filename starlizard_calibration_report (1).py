"""PRO STARLIZARD: read-only walk-forward calibration and baseline comparison.

Uses only Supabase historical_xg; no API calls, writes or market-price claims.
Run with the same environment variables as starlizard_walkforward_backtest.py.
"""
import numpy as np
import pandas as pd
from supabase import create_client
from starlizard_pricing_engine import clean_history, fit_ratings, price_fixture, standard_markets, score_matrix
from starlizard_walkforward_backtest import (COMPETITION, START, END, MIN_TRAIN,
                                              MAX_DATES, fetch)
import os


def score(rows, prefix):
    p = np.clip(rows[[f'{prefix}_{k}' for k in ('home','draw','away')]].to_numpy(float), 1e-12, 1)
    outcomes = rows['outcome'].to_numpy(int)
    onehot = np.eye(3)[outcomes]
    brier = np.mean(np.sum((p-onehot)**2, axis=1))
    logloss = np.mean(-np.log(p[np.arange(len(rows)), outcomes]))
    print(f'{prefix}: 1X2 Brier {brier:.5f}; log loss {logloss:.5f}')
    for market in ('over25', 'btts'):
        probs = rows[f'{prefix}_{market}'].to_numpy(float)
        actual = rows[f'actual_{market}'].to_numpy(float)
        print(f'  {market}: Brier {np.mean((probs-actual)**2):.5f}; predicted {probs.mean():.1%}; actual {actual.mean():.1%}')


def main():
    db = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SECRET_KEY'])
    raw = fetch(db)
    history = clean_history(raw, COMPETITION, END)
    actual = raw[['match_id','home_goals','away_goals']].drop_duplicates('match_id', keep='last').copy()
    for col in ('home_goals','away_goals'):
        actual[col] = pd.to_numeric(actual[col], errors='coerce')
    data = history.merge(actual, on='match_id', how='inner').dropna(subset=['home_goals','away_goals'])
    data = data[(data.home_goals >= 0)&(data.away_goals >= 0)&
                (data.home_goals % 1 == 0)&(data.away_goals % 1 == 0)].copy()
    data['day'] = data.match_date.dt.strftime('%Y-%m-%d')
    dates = sorted(d for d in data.day.unique() if START <= d < END)
    if MAX_DATES > 0:
        dates = dates[:MAX_DATES]
    results = []
    for day in dates:
        cutoff = pd.Timestamp(day, tz='UTC')
        training = history[history.match_date < cutoff]
        training_goals = data[data.match_date < cutoff]
        if len(training) < MIN_TRAIN or len(training_goals) < MIN_TRAIN:
            continue
        ratings = fit_ratings(training, COMPETITION, day, minimum_matches=MIN_TRAIN)
        # Deliberately simple benchmark: past league-wide mean actual home and away goals.
        baseline_home = float(training_goals.home_goals.mean())
        baseline_away = float(training_goals.away_goals.mean())
        baseline = standard_markets(score_matrix(baseline_home, baseline_away))
        for m in data[data.day == day].itertuples(index=False):
            if m.home_team not in ratings.teams or m.away_team not in ratings.teams:
                continue
            pred = price_fixture(ratings, m.home_team, m.away_team)
            probs = pred['probabilities']
            outcome = 0 if m.home_goals > m.away_goals else (2 if m.home_goals < m.away_goals else 1)
            record = {'date':day, 'outcome':outcome,
                      'actual_over25':int(m.home_goals+m.away_goals >= 3),
                      'actual_btts':int(m.home_goals>0 and m.away_goals>0),
                      'predicted_total_goals':pred['home_xg']+pred['away_xg'],
                      'actual_total_goals':m.home_goals+m.away_goals}
            for name, p in (('model',probs),('baseline',baseline)):
                for key in ('home','draw','away'):
                    record[f'{name}_{key}'] = p[key]
                record[f'{name}_over25'] = p['over_2_5']
                record[f'{name}_btts'] = p['btts_yes']
            results.append(record)
    if not results:
        raise RuntimeError('No predictions; check cutoff and training data')
    r = pd.DataFrame(results)
    print(f'CALIBRATION AND BENCHMARK REPORT: {len(r)} predictions over {r.date.nunique()} dates')
    print('Strict prior-date training; baseline uses historical league-average actual goals')
    score(r, 'model')
    score(r, 'baseline')
    print(f'Mean predicted total goals {r.predicted_total_goals.mean():.3f}; actual {r.actual_total_goals.mean():.3f}')
    for market in ('over25','btts'):
        print(f'CALIBRATION BINS: {market} (model probabilities)')
        for low, high in ((0,.3),(.3,.4),(.4,.5),(.5,.6),(.6,1.00001)):
            sub = r[(r[f'model_{market}'] >= low)&(r[f'model_{market}'] < high)]
            if len(sub):
                print(f'  {low:.0%}-{min(high,1):.0%}: n={len(sub)} predicted={sub[f"model_{market}"].mean():.1%} actual={sub[f"actual_{market}"].mean():.1%}')
    print('Research only. Small bins are noisy; no calibration or betting edge established.')


if __name__ == '__main__':
    main()
