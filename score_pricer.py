"""Consistent pre-match and conditional in-play Poisson score pricing.
Research-only: independent Poisson, no market calibration, red cards, or injury time.
"""
import argparse
import csv
import math
from pathlib import Path


def poisson_probs(rate, maximum=18):
    if rate < 0 or not math.isfinite(rate):
        raise ValueError('Expected goals must be finite and nonnegative')
    p = [math.exp(-rate)]
    for k in range(1, maximum + 1):
        p.append(p[-1] * rate / k)
    # Accumulate tiny remaining tail into last bin (18+ goals)
    p[-1] += max(0., 1. - sum(p))
    return p


def price(home_xg, away_xg, score_home=0, score_away=0, remaining_fraction=1., maximum=18):
    if not 0 <= remaining_fraction <= 1:
        raise ValueError('remaining_fraction must be between zero and one')
    hp = poisson_probs(home_xg * remaining_fraction, maximum)
    ap = poisson_probs(away_xg * remaining_fraction, maximum)
    matrix = [[h*a for a in ap] for h in hp]
    home = draw = away = over25 = btts = 0.
    scores = {}
    for i, row in enumerate(matrix):
        for j, prob in enumerate(row):
            h, a = score_home+i, score_away+j
            if h > a: home += prob
            elif h == a: draw += prob
            else: away += prob
            if h+a >= 3: over25 += prob
            if h > 0 and a > 0: btts += prob
            if h <= 7 and a <= 7: scores[f'{h}-{a}'] = prob
    # Goal lines and Asian handicap can be derived from same matrix later.
    probs = {'home':home, 'draw':draw, 'away':away, 'over25':over25, 'under25':1-over25,
             'btts_yes':btts, 'btts_no':1-btts}
    return {'probabilities':probs, 'fair_odds':{k:(1/v if v > 0 else None) for k,v in probs.items()},
            'scores':scores, 'score_fair_odds':{k:1/v if v>0 else None for k,v in scores.items()},
            'normalization':sum(sum(r) for r in matrix)}


def edge(probability, bookmaker_decimal_odds, commission=0):
    if not 0 <= commission < 1 or bookmaker_decimal_odds <= 1:
        raise ValueError('Invalid commission or bookmaker odds')
    net_odds = 1+(bookmaker_decimal_odds-1)*(1-commission)
    return probability*net_odds-1


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--predictions',default='predictions.csv')
    parser.add_argument('--row',type=int,default=0,help='Zero-based prediction row')
    parser.add_argument('--home-goals',type=int,default=0)
    parser.add_argument('--away-goals',type=int,default=0)
    parser.add_argument('--remaining',type=float,default=1.,help='Fraction of match remaining, not clock minutes')
    args=parser.parse_args()
    with open(args.predictions,newline='',encoding='utf-8') as f:
        record=next(r for i,r in enumerate(csv.DictReader(f)) if i==args.row)
    result=price(float(record['lambda_home']),float(record['lambda_away']),args.home_goals,args.away_goals,args.remaining)
    print(f"{record['home_team']} vs {record['away_team']} | historical {record['date']}")
    print('Market          Probability   Fair odds')
    for name, p in result['probabilities'].items():
        print(f'{name:16}{p:8.2%}    {result["fair_odds"][name]:8.2f}')
    print('Top 10 correct scores:')
    for name, p in sorted(result['scores'].items(),key=lambda item:item[1],reverse=True)[:10]:
        print(f'{name:6} {p:8.2%}    {1/p:8.2f}')

if __name__=='__main__':
    main()
