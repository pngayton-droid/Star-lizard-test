"""PRO STARLIZARD: read-only walk-forward goal-rate adjustment experiment.

Uses only prior-date Supabase historical_xg records. No StatsAPI calls or writes.
The adjustment is a pre-specified historical actual-goals / xG ratio, not fitted
on evaluation fixtures. Research experiment; not a production calibration.
"""
import os
import numpy as np
import pandas as pd
from supabase import create_client
from starlizard_pricing_engine import clean_history, fit_ratings, score_matrix, standard_markets
from starlizard_walkforward_backtest import COMPETITION, START, END, MIN_TRAIN, MAX_DATES, fetch

MARKETS = ('home', 'draw', 'away', 'over_2_5', 'btts_yes')


def evaluate(rows, label):
    p = np.array([[r[f'{label}_{k}'] for k in ('home', 'draw', 'away')] for r in rows])
    y = np.array([r['outcome'] for r in rows], dtype=int)
    brier = np.mean(np.sum((p - np.eye(3)[y]) ** 2, axis=1))
    logloss = -np.log(np.clip(p[np.arange(len(y)), y], 1e-12, 1)).mean()
    print(f'{label}: 1X2 Brier={brier:.5f}; log loss={logloss:.5f}')
    for market, actual in (('over_2_5', 'actual_over25'), ('btts_yes', 'actual_btts')):
        probabilities = np.array([r[f'{label}_{market}'] for r in rows])
        observed = np.array([r[actual] for r in rows])
        print(f'  {market}: Brier={np.mean((probabilities-observed)**2):.5f}; '
              f'predicted={probabilities.mean():.1%}; actual={observed.mean():.1%}')


def main():
    db = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SECRET_KEY'])
    raw = fetch(db)
    history = clean_history(raw, COMPETITION, END)
    goals = raw[['match_id', 'home_goals', 'away_goals']].drop_duplicates('match_id', keep='last').copy()
    for c in ('home_goals', 'away_goals'):
        goals[c] = pd.to_numeric(goals[c], errors='coerce')
    data = history.merge(goals, on='match_id', how='inner').dropna(subset=['home_goals', 'away_goals'])
    data = data[(data.home_goals >= 0) & (data.away_goals >= 0) &
                (data.home_goals % 1 == 0) & (data.away_goals % 1 == 0)].copy()
    data['day'] = data.match_date.dt.strftime('%Y-%m-%d')
    dates = sorted(d for d in data.day.unique() if START <= d < END)
    if MAX_DATES > 0:
        dates = dates[:MAX_DATES]
    results = []
    ratios = []
    for day in dates:
        cutoff = pd.Timestamp(day, tz='UTC')
        prior_xg = history[history.match_date < cutoff]
        prior_goals = data[data.match_date < cutoff]
        if len(prior_xg) < MIN_TRAIN or len(prior_goals) < MIN_TRAIN:
            continue
        ratings = fit_ratings(prior_xg, COMPETITION, day, minimum_matches=MIN_TRAIN)
        # Predefined, smoothed and bounded prior-only adjustment.
        # 100-goal prior shrinks the ratio towards 1, without looking at test outcomes.
        total_actual = float((prior_goals.home_goals + prior_goals.away_goals).sum())
        total_xg = float((prior_goals.home_xg + prior_goals.away_xg).sum())
        ratio = float(np.clip((total_actual + 100.0) / (total_xg + 100.0), 0.8, 1.25))
        ratios.append(ratio)
        base_home = float(prior_goals.home_goals.mean())
        base_away = float(prior_goals.away_goals.mean())
        baseline = standard_markets(score_matrix(base_home, base_away))
        for match in data[data.day == day].itertuples(index=False):
            if match.home_team not in ratings.teams or match.away_team not in ratings.teams:
                continue
            home_xg, away_xg = ratings.expected_goals(match.home_team, match.away_team)
            original = standard_markets(score_matrix(home_xg, away_xg))
            adjusted = standard_markets(score_matrix(home_xg * ratio, away_xg * ratio))
            record = {
                'outcome': 0 if match.home_goals > match.away_goals else (1 if match.home_goals == match.away_goals else 2),
                'actual_over25': int(match.home_goals + match.away_goals >= 3),
                'actual_btts': int(match.home_goals > 0 and match.away_goals > 0),
                'actual_total': float(match.home_goals + match.away_goals),
                'original_total': home_xg + away_xg,
                'adjusted_total': (home_xg + away_xg) * ratio,
            }
            for label, probs in (('original', original), ('adjusted', adjusted), ('baseline', baseline)):
                for market in MARKETS:
                    record[f'{label}_{market}'] = probs[market]
            results.append(record)
    if not results:
        raise RuntimeError('No eligible test fixtures. Check competition, dates and training minimum.')
    print(f'GOAL CALIBRATION EXPERIMENT: {len(results)} fixtures across {len(ratios)} match dates')
    print('All model fits, benchmark rates and adjustment ratios use strictly earlier dates.')
    print('Predefined adjustment = clip((prior actual goals + 100)/(prior xG + 100), 0.8, 1.25).')
    print(f'Adjustment ratio range across dates: {min(ratios):.3f} to {max(ratios):.3f}')
    for label in ('original', 'adjusted', 'baseline'):
        evaluate(results, label)
    print('Mean total goals: original={:.3f}; adjusted={:.3f}; actual={:.3f}'.format(
        np.mean([r['original_total'] for r in results]),
        np.mean([r['adjusted_total'] for r in results]),
        np.mean([r['actual_total'] for r in results])))
    print('Research only. Adjustment may not improve accuracy; no betting edge established.')


if __name__ == '__main__':
    main()
