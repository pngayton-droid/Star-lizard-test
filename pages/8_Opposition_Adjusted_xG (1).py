"""Pro Star Lizard: cautious, API-based opponent-adjusted xG prototype."""
import math
import os
import time
from datetime import date

import numpy as np
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title='Star Lizard | xG Strength', layout='centered')
st.title('Pro Star Lizard | Opposition-adjusted xG')
st.caption('Experimental team ratings from TheStatsAPI. No bookmaker edge or predictive accuracy has yet been established.')
BASE = 'https://api.thestatsapi.com/api'
key = st.secrets.get('STATS_API_KEY', os.environ.get('STATS_API_KEY', ''))
if not key:
    st.error('STATS_API_KEY is missing from Streamlit secrets.')
    st.stop()

for name, default in [('sl_stats_cache', {}), ('sl_match_cache', {}), ('sl_last_call', 0.0)]:
    if name not in st.session_state:
        st.session_state[name] = default

session = requests.Session()
session.headers.update({'Authorization': f'Bearer {key}', 'Accept': 'application/json'})

def api(path, params=None):
    for attempt in range(4):
        elapsed = time.monotonic() - st.session_state.sl_last_call
        if elapsed < 1.7:
            time.sleep(1.7 - elapsed)
        st.session_state.sl_last_call = time.monotonic()
        try:
            response = session.get(BASE + path, params=params, timeout=30)
        except requests.RequestException as exc:
            if attempt == 3:
                return None, str(exc)
            time.sleep(4 * (attempt + 1))
            continue
        if response.status_code == 200:
            try:
                return response.json().get('data'), None
            except ValueError:
                return None, 'Invalid API JSON'
        if response.status_code == 429 and attempt < 3:
            try:
                retry = float(response.headers.get('Retry-After', '0'))
            except ValueError:
                retry = 0
            wait = min(120, max(retry, (15, 30, 60)[attempt]))
            st.info(f'API rate limit; waiting {wait:.0f}s before retry.')
            time.sleep(wait)
            continue
        return None, f'HTTP {response.status_code}: {response.text[:180]}'
    return None, 'API retries exhausted'

def matches(team_id, count, cutoff):
    cache_key = (team_id, count, cutoff)
    if cache_key in st.session_state.sl_match_cache:
        return st.session_state.sl_match_cache[cache_key], None
    data, err = api('/football/matches', {'team_id': team_id, 'status': 'finished', 'date_to': cutoff,
                                        'per_page': count, 'page': 1, 'sort': '-utc_date'})
    if err:
        return [], err
    if not isinstance(data, list):
        return [], 'Unexpected match-list response'
    result = [m for m in data if isinstance(m, dict) and m.get('id')]
    st.session_state.sl_match_cache[cache_key] = result
    return result, None

def stats(mid):
    if mid in st.session_state.sl_stats_cache:
        return st.session_state.sl_stats_cache[mid], None
    data, err = api(f'/football/matches/{mid}/stats')
    if isinstance(data, dict) and not err:
        st.session_state.sl_stats_cache[mid] = data
    return data, err

def read_xg(data, side):
    if not isinstance(data, dict):
        return None
    for section in data.values():
        if isinstance(section, dict) and 'expected_goals' in section:
            value = section['expected_goals']
            if isinstance(value, dict) and isinstance(value.get('all'), dict):
                try:
                    v = float(value['all'][side])
                    return v if math.isfinite(v) and v >= 0 else None
                except (TypeError, ValueError, KeyError):
                    return None
    return None

def build_rows(all_matches, cutoff):
    rows, errors = [], []
    ids = list(all_matches)
    bar = st.progress(0, text='Collecting xG')
    for i, mid in enumerate(ids):
        m = all_matches[mid]
        h = m.get('home_team') or {}
        a = m.get('away_team') or {}
        if h.get('id') and a.get('id'):
            data, err = stats(mid)
            if err:
                errors.append(f'{mid}: {err}')
            else:
                hx, ax = read_xg(data, 'home'), read_xg(data, 'away')
                if hx is not None and ax is not None:
                    d = str(m.get('utc_date', ''))[:10]
                    try:
                        age = max(0, (date.fromisoformat(cutoff) - date.fromisoformat(d)).days)
                    except ValueError:
                        age = 365
                    rows.append({'Date': d, 'Home ID': h['id'], 'Home': h.get('name', ''),
                                 'Away ID': a['id'], 'Away': a.get('name', ''),
                                 'Home xG': hx, 'Away xG': ax, 'Age': age, 'Match ID': mid})
        bar.progress((i+1)/max(1,len(ids)), text=f'xG checked: {i+1}/{len(ids)}')
    return pd.DataFrame(rows), errors

def fit_ratings(df, half_life, ridge):
    """Weighted ridge fit: log(xG+.15)=intercept+attack(team)-defence(opponent)+home effect.
    Both team effects have zero-centred priors. Shrinkage guards sparse schedules.
    """
    teams = sorted(set(df['Home ID']) | set(df['Away ID']))
    idx = {t:i for i,t in enumerate(teams)}
    n = len(teams)
    X, y, weights = [], [], []
    for r in df.itertuples(index=False):
        # Use position-based tuple values to avoid pandas column-name munging.
        vals = list(r)
        h, a = idx[vals[1]], idx[vals[3]]
        w = 2 ** (-float(vals[7]) / half_life)
        for attack, defence, homeflag, xg in [(h,a,1,vals[5]), (a,h,0,vals[6])]:
            row = np.zeros(2+2*n)
            row[0] = 1
            row[1] = homeflag
            row[2+attack] = 1
            row[2+n+defence] = -1
            X.append(row)
            y.append(math.log(float(xg)+.15))
            weights.append(w)
    X = np.asarray(X)
    y = np.asarray(y)
    sw = np.sqrt(np.asarray(weights))
    penalty = np.eye(X.shape[1]) * ridge
    penalty[0,0] = .001
    penalty[1,1] = ridge * 2
    beta = np.linalg.solve((X*sw[:,None]).T @ (X*sw[:,None]) + penalty,
                           (X*sw[:,None]).T @ (y*sw))
    return teams, idx, beta

def poisson_grid(hxg, axg, cap=20):
    def probs(lam):
        arr = [math.exp(-lam)]
        for k in range(1,cap+1):
            arr.append(arr[-1]*lam/k)
        return arr
    ph, pa = probs(hxg), probs(axg)
    return [(h,a,ph[h]*pa[a]) for h in range(cap+1) for a in range(cap+1)]

def settle_one(diff):
    return 1 if diff > 1e-9 else (-1 if diff < -1e-9 else 0)

def settle(diff, line):
    q = round(line*4)
    if q % 2:
        lower = math.floor(line*2)/2
        upper = lower+.5
        return (settle_one(diff+lower)+settle_one(diff+upper))/2
    return settle_one(diff+line)

def asian_price(grid, market, line):
    outcomes = {1:0.,.5:0.,0:0.,-.5:0.,-1:0.}
    for h,a,p in grid:
        diff = {'Home handicap':h-a,'Away handicap':a-h,
                'Over goals':h+a,'Under goals':-h-a}[market]
        effective_line = -line if market == 'Over goals' else line
        outcomes[settle(diff,effective_line)] += p
    w = outcomes[1]+.5*outcomes[.5]
    loss = outcomes[-1]+.5*outcomes[-.5]
    return (1+loss/w if w else float('inf')), outcomes, w, loss

st.subheader('1. Select teams')
st.caption('Initial test: Newcastle v Everton. Enter API team IDs to analyse other fixtures; league-wide ingestion comes later.')
col1,col2 = st.columns(2)
with col1:
    home_id = st.text_input('Home team API ID', 'tm_7938')
with col2:
    away_id = st.text_input('Away team API ID', 'tm_8091')
count = st.slider('Matches per primary team', 10, 30, 20, 5)
extra = st.slider('Opponent teams to sample (per side)', 0, 10, 5, 1)
opp_count = st.slider('Matches per sampled opponent', 5, 15, 8, 1)
cutoff = st.date_input('Completed by', date.today())
half_life = st.slider('Recency half-life (days)', 60, 365, 180, 30)
ridge = st.slider('Rating shrinkage', 2.0, 30.0, 10.0, 2.0)
st.caption('Opponent samples expand the network of team strengths. Start small: the API rate limit may make larger runs slow.')

if st.button('Build opponent-adjusted xG ratings', type='primary'):
    if not home_id.strip() or not away_id.strip() or home_id == away_id:
        st.error('Enter two different valid team IDs.')
    else:
        with st.spinner('Fetching and fitting historical xG...'):
            all_matches, errors = {}, []
            primary = {}
            for tid in (home_id.strip(), away_id.strip()):
                ms, err = matches(tid, count, cutoff.isoformat())
                if err:
                    errors.append(f'{tid}: {err}')
                primary[tid] = ms
                for m in ms:
                    all_matches[m['id']] = m
            opponent_ids = []
            for tid, ms in primary.items():
                if extra == 0:
                    continue
                seen = set()
                for m in ms:
                    for side in ('home_team','away_team'):
                        oid = (m.get(side) or {}).get('id')
                        if oid and oid not in (home_id,away_id) and oid not in seen:
                            seen.add(oid)
                            opponent_ids.append(oid)
                            if len(seen) >= extra:
                                break
                    if len(seen) >= extra:
                        break
            for oid in dict.fromkeys(opponent_ids):
                ms, err = matches(oid, opp_count, cutoff.isoformat())
                if err:
                    errors.append(f'{oid}: {err}')
                for m in ms:
                    all_matches[m['id']] = m
            df, detail_errors = build_rows(all_matches, cutoff.isoformat())
            errors += detail_errors
            if len(df) < 15:
                st.error(f'Only {len(df)} matches with usable xG. No ratings calculated.')
            else:
                try:
                    teams, idx, beta = fit_ratings(df, half_life, ridge)
                    if home_id not in idx or away_id not in idx:
                        raise ValueError('Selected team missing from usable match data')
                    h, a = idx[home_id], idx[away_id]
                    hxg = max(.1,min(5.,math.exp(beta[0]+beta[1]+beta[2+h]-beta[2+len(teams)+a])-.15))
                    axg = max(.1,min(5.,math.exp(beta[0]+beta[2+a]-beta[2+len(teams)+h])-.15))
                    st.session_state.sl_rating_result = (df, errors, teams, beta, hxg, axg, home_id, away_id)
                except (ValueError, np.linalg.LinAlgError) as exc:
                    st.error(f'Could not fit ratings: {exc}')

result = st.session_state.get('sl_rating_result')
if not result:
    st.info('Run the model above to obtain ratings. No placeholder prices are shown.')
    st.stop()
df, errors, teams, beta, hxg, axg, fitted_home, fitted_away = result
if fitted_home != home_id or fitted_away != away_id:
    st.warning('Team IDs changed since the last run. Rebuild ratings before using these prices.')
    st.stop()
st.subheader('2. Adjusted xG projections')
c1,c2 = st.columns(2)
c1.metric('Home projected xG', f'{hxg:.2f}')
c2.metric('Away projected xG', f'{axg:.2f}')
st.write(f'**{len(df)}** unique matches with xG · **{len(teams)}** teams in rating network')
st.caption('Weighted, regularised attack/defence regression on log(xG + 0.15), with home advantage. Sparse teams shrink toward average. Not calibrated or validated; this is an exploratory model.')
if errors:
    st.warning(f'{len(errors)} API requests failed. Ratings use available records only.')
    with st.expander('API failures'):
        st.write(errors)
with st.expander('Evidence and export'):
    st.dataframe(df[['Date','Home','Away','Home xG','Away xG']],hide_index=True,use_container_width=True)
    st.download_button('Download training matches CSV', df.to_csv(index=False), 'starlizard_rating_matches.csv','text/csv')

st.subheader('3. Asian pricing from adjusted xG')
market = st.selectbox('Market', ['Home handicap','Away handicap','Over goals','Under goals'])
lines = [i/4 for i in range(-12,13)] if 'handicap' in market else [i/4 for i in range(2,25)]
default = 0.0 if 'handicap' in market else 2.5
line = st.selectbox('Asian line', lines, index=lines.index(default))
grid = poisson_grid(hxg,axg)
fair, outcomes, w, loss = asian_price(grid,market,line)
st.metric('Experimental fair odds', f'{fair:.3f}')
st.write(f'Full win {outcomes[1]:.1%} · Half win {outcomes[.5]:.1%} · Push {outcomes[0]:.1%}')
st.write(f'Half loss {outcomes[-.5]:.1%} · Full loss {outcomes[-1]:.1%}')
quote = st.number_input('Bookmaker odds (comparison only)', min_value=1.01, max_value=100.0, value=1.95, step=.01)
st.metric('Conditional model ROI', f'{w*(quote-1)-loss:+.2%}')
st.warning('Do not interpret positive ROI as a verified edge. Ratings require out-of-sample testing, competition controls, and model calibration.')
