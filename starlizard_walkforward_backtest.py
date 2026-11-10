"""PRO STARLIZARD: read-only, chronological out-of-sample backtest.

Usage: python starlizard_walkforward_backtest.py
Requires SUPABASE_URL and SUPABASE_SECRET_KEY environment variables.
No TheStatsAPI calls and no database writes.
"""
import os
import numpy as np
import pandas as pd
from supabase import create_client
from starlizard_pricing_engine import clean_history, fit_ratings, price_fixture

COMPETITION = os.getenv('BACKTEST_COMPETITION', 'comp_3039')
START = os.getenv('BACKTEST_START', '2025-08-01')
END = os.getenv('BACKTEST_END', '2026-11-10')  # exclusive
MIN_TRAIN = int(os.getenv('BACKTEST_MIN_TRAIN', '100'))
MAX_DATES = int(os.getenv('BACKTEST_MAX_DATES', '12'))
COLUMNS = ('match_id,competition_id,match_date,home_team,away_team,'
           'home_xg,away_xg,home_goals,away_goals')


def fetch(db):
    rows = []
    offset = 0
    while True:
        result = (db.table('historical_xg').select(COLUMNS)
                  .eq('competition_id', COMPETITION).lt('match_date', END)
                  .order('match_date').order('match_id')
                  .range(offset, offset + 499).execute())
        batch = result.data or []
        rows.extend(batch)
        if len(batch) < 500:
            break
        offset += 500
    return pd.DataFrame(rows)


def main():
    url = os.environ['SUPABASE_URL']
    key = os.environ['SUPABASE_SECRET_KEY']
    db = create_client(url, key)
    raw = fetch(db)
    history = clean_history(raw, COMPETITION, END)
    if history.empty:
        raise RuntimeError('No usable historical xG')
    actual = raw[['match_id', 'home_goals', 'away_goals']].copy()
    for col in ('home_goals', 'away_goals'):
        actual[col] = pd.to_numeric(actual[col], errors='coerce')
    actual = actual.drop_duplicates('match_id', keep='last')
    data = history.merge(actual, on='match_id', how='left')
    data = data.dropna(subset=['home_goals', 'away_goals'])
    data = data[(data.home_goals >= 0) & (data.away_goals >= 0)]
    data = data[(data.home_goals % 1 == 0) & (data.away_goals % 1 == 0)]
    data['day'] = data.match_date.dt.strftime('%Y-%m-%d')
    dates = sorted(day for day in data.day.unique() if START <= day < END)
    if MAX_DATES > 0:
        dates = dates[:MAX_DATES]
    results = []
    for day in dates:
        training = history[history.match_date < pd.Timestamp(day, tz='UTC')]
        if len(training) < MIN_TRAIN:
            print(f'{day}: skip, {len(training)} training matches')
            continue
        ratings = fit_ratings(training, COMPETITION, day, minimum_matches=MIN_TRAIN)
        matches = data[data.day == day]
        predicted = 0
        for r in matches.itertuples(index=False):
            if r.home_team not in ratings.teams or r.away_team not in ratings.teams:
                continue
            p = price_fixture(ratings, r.home_team, r.away_team)['probabilities']
            outcome = 'home' if r.home_goals > r.away_goals else ('away' if r.home_goals < r.away_goals else 'draw')
            total = int(r.home_goals + r.away_goals >= 3)
            btts = int(r.home_goals > 0 and r.away_goals > 0)
            results.append({'date':day, 'home':r.home_team, 'away':r.away_team,
                            'actual':outcome, 'p_home':p['home'], 'p_draw':p['draw'],
                            'p_away':p['away'], 'p_over25':p['over_2_5'],
                            'actual_over25':total, 'p_btts':p['btts_yes'],
                            'actual_btts':btts, 'training_matches':ratings.matches})
            predicted += 1
        print(f'{day}: {predicted} predictions; {ratings.matches} prior training matches')
    if not results:
        raise RuntimeError('No out-of-sample predictions. Increase MAX_DATES or adjust START.')
    r = pd.DataFrame(results)
    brier_1x2 = np.mean(sum((r['p_'+k] - (r.actual == k).astype(int))**2 for k in ('home','draw','away')))
    true_p = np.array([row['p_'+row['actual']] for _,row in r.iterrows()])
    logloss = -np.log(np.clip(true_p, 1e-12, 1)).mean()
    print('\nOUT-OF-SAMPLE SUMMARY')
    print(f'Predictions: {len(r)} across {r.date.nunique()} dates')
    print(f'1X2 multiclass Brier (lower better): {brier_1x2:.5f}')
    print(f'1X2 log loss (lower better): {logloss:.5f}')
    for label, prob, observed in [('Over 2.5', 'p_over25', 'actual_over25'),
                                   ('BTTS Yes', 'p_btts', 'actual_btts')]:
        bs = np.mean((r[prob] - r[observed])**2)
        print(f'{label}: Brier {bs:.5f}; mean predicted {r[prob].mean():.1%}; actual {r[observed].mean():.1%}')
    print('Research only: no market comparison, no calibration or betting edge established.')


if __name__ == '__main__':
    main()
