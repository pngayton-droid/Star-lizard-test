"""Pro Star Lizard — transparent experimental Asian pricing lab.

Independent Streamlit page. Uses a basic independent Poisson model; not validated
against market odds or historical outcomes. No API key required.
"""
import math
from itertools import product

import pandas as pd
import streamlit as st

st.set_page_config(page_title='Star Lizard | Asian Pricing Lab', layout='wide')
st.title('Pro Star Lizard | Asian Pricing Lab')
st.caption('Experimental independent-Poisson prices. Model inputs are assumptions, not verified predictions or betting recommendations.')

st.subheader('1. Expected goals')
col1, col2 = st.columns(2)
with col1:
    home_name = st.text_input('Home team', 'Newcastle United')
    home_xg = st.number_input('Home expected goals (model input)', 0.05, 6.0, 1.55, 0.05)
with col2:
    away_name = st.text_input('Away team', 'Everton')
    away_xg = st.number_input('Away expected goals (model input)', 0.05, 6.0, 1.35, 0.05)
st.info('The starting expected-goal inputs are illustrative, NOT estimates derived from the Newcastle/Everton historical data. Adjust them or replace them with calibrated model outputs.')

@st.cache_data
def outcome_grid(hxg, axg, cap=24):
    def probs(lam):
        p = math.exp(-lam)
        result = [p]
        for n in range(1, cap + 1):
            p *= lam / n
            result.append(p)
        return result
    hp, ap = probs(hxg), probs(axg)
    grid = [(h, a, ph * pa) for (h, ph), (a, pa) in product(enumerate(hp), enumerate(ap))]
    return grid, 1 - sum(p for _, _, p in grid)


def leg_result(value):
    """One full Asian line leg, expressed as win fraction (1), push (0), loss (-1)."""
    if value > 1e-9:
        return 1
    if value < -1e-9:
        return -1
    return 0


def settle(score_diff, line):
    """Asian lines are multiples of .25; quarter lines split into adjacent half-lines."""
    q = round(line * 4)
    if abs(line * 4 - q) > 1e-7:
        raise ValueError('Line must be a multiple of 0.25')
    if q % 2:
        lower = math.floor(line * 2) / 2
        upper = lower + 0.5
        return (leg_result(score_diff + lower) + leg_result(score_diff + upper)) / 2
    return leg_result(score_diff + line)


def price_line(grid, kind, line):
    bins = {1: 0.0, 0.5: 0.0, 0: 0.0, -0.5: 0.0, -1: 0.0}
    for h, a, p in grid:
        if kind == 'Home handicap':
            margin = h - a
        elif kind == 'Away handicap':
            margin = a - h
        elif kind == 'Over goals':
            margin = h + a
            line = -abs(line)
        elif kind == 'Under goals':
            margin = -(h + a)
        else:
            raise ValueError(kind)
        result = settle(margin, line)
        bins[result] += p
    win_share = bins[1] + 0.5 * bins[0.5]
    loss_share = bins[-1] + 0.5 * bins[-0.5]
    fair = 1 + loss_share / win_share if win_share > 0 else float('inf')
    return bins, win_share, loss_share, fair


grid, tail = outcome_grid(home_xg, away_xg)
if tail > 1e-7:
    st.warning(f'Unmodelled high-score probability: {tail:.7%}. Increase score-grid cap.')

st.subheader('2. Asian handicap — both sides')
handicap_lines = [i / 4 for i in range(-12, 13)]

def record(kind, line):
    bins, w, l, fair = price_line(grid, kind, line)
    return {'Market': kind, 'Line': f'{line:+.2f}', 'Fair odds': round(fair, 3),
            'Full win %': round(100 * bins[1], 2), 'Half win %': round(100 * bins[0.5], 2),
            'Push %': round(100 * bins[0], 2), 'Half loss %': round(100 * bins[-0.5], 2),
            'Full loss %': round(100 * bins[-1], 2)}

handicaps = pd.DataFrame([record(kind, line) for line in handicap_lines
                         for kind in ('Home handicap', 'Away handicap')])
st.dataframe(handicaps, use_container_width=True, hide_index=True)

st.subheader('3. Asian goal totals — over and under')
total_lines = [i / 4 for i in range(2, 21)]
totals = pd.DataFrame([record(kind, line) for line in total_lines
                       for kind in ('Over goals', 'Under goals')])
st.dataframe(totals, use_container_width=True, hide_index=True)

st.subheader('4. Compare with a market quote')
q1, q2, q3 = st.columns(3)
with q1:
    selected_kind = st.selectbox('Market', ['Home handicap', 'Away handicap', 'Over goals', 'Under goals'])
with q2:
    options = handicap_lines if 'handicap' in selected_kind else total_lines
    selected_line = st.selectbox('Asian line', options, index=options.index(0.0) if 0.0 in options else options.index(2.5))
with q3:
    quoted_odds = st.number_input('Bookmaker decimal odds', 1.01, 1000.0, 1.95, 0.01)

bins, win, loss, fair = price_line(grid, selected_kind, selected_line)
ev = win * (quoted_odds - 1) - loss
c1, c2, c3 = st.columns(3)
c1.metric('Model fair odds', f'{fair:.3f}')
c2.metric('Expected return per £1', f'{ev:+.3f}')
c3.metric('Model ROI', f'{ev * 100:+.2f}%')
st.caption('ROI includes full/half wins, pushes and full/half losses. Positive model ROI is NOT evidence of a real-world edge; xG inputs, calibration, bookmaker margin and model error matter.')
st.write('Settlement probabilities:', {k: f'{100 * v:.2f}%' for k, v in bins.items()})

st.subheader('5. Export prices')
combined = pd.concat([handicaps, totals], ignore_index=True)
st.download_button('Download Asian fair-price table (CSV)',
                   combined.to_csv(index=False).encode('utf-8'),
                   file_name='starlizard_asian_prices.csv', mime='text/csv')
st.caption('Next phase: estimate goal expectations from historical fixtures and bookmaker-independent team ratings, then validate out of sample. Corners need their own count model, not the goal inputs used here.')
