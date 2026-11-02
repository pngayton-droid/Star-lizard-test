"""Pro Star Lizard | API-connected Asian pricing (experimental)."""
import math
import os
import time
from datetime import datetime, timezone
from itertools import product
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title='Star Lizard | Live Historical Asian Lab', layout='centered')
st.title('Pro Star Lizard | API Asian Pricing Lab')
st.caption('Latest completed-match statistics from TheStatsAPI. Prices are experimental, uncalibrated estimates, not betting recommendations.')
BASE = 'https://api.thestatsapi.com/api'
HOME_ID, AWAY_ID = 'tm_7938', 'tm_8091'
key = st.secrets.get('STATS_API_KEY', os.environ.get('STATS_API_KEY', ''))
if not key:
    st.error('STATS_API_KEY is missing from Streamlit secrets. Do not paste it into chat.')
    st.stop()
session = requests.Session()
session.headers.update({'Authorization': f'Bearer {key}', 'Accept': 'application/json'})
if 'historical_stats_cache' not in st.session_state:
    st.session_state.historical_stats_cache = {}
if 'historical_last_request' not in st.session_state:
    st.session_state.historical_last_request = 0.0

@st.cache_data
def outcome_grid(hxg, axg, cap=25):
    def poisson(lam):
        p = math.exp(-lam)
        result = [p]
        for n in range(1, cap + 1):
            p *= lam / n
            result.append(p)
        return result
    hp, ap = poisson(hxg), poisson(axg)
    grid = [(h, a, x*y) for (h,x),(a,y) in product(enumerate(hp), enumerate(ap))]
    return grid, 1-sum(p for _,_,p in grid)

def leg(v):
    return (v > 1e-9) - (v < -1e-9)

def settle(diff, line):
    q = round(line*4)
    if abs(line*4-q)>1e-7:
        raise ValueError('Quarter-line increments required')
    if q%2:
        lower = math.floor(line*2)/2
        return (leg(diff+lower)+leg(diff+lower+0.5))/2
    return leg(diff+line)

def price(grid, kind, line):
    bins = {1:0., .5:0., 0:0., -.5:0., -1:0.}
    for h,a,p in grid:
        diff = {'Home handicap':h-a, 'Away handicap':a-h,
                'Over goals':h+a, 'Under goals':-h-a}[kind]
        effective_line = -line if kind=='Over goals' else line
        bins[settle(diff,effective_line)] += p
    w = bins[1]+.5*bins[.5]
    l = bins[-1]+.5*bins[-.5]
    return bins, (1+l/w if w else float('inf')), w, l


def api(path, params=None, max_retries=3):
    for attempt in range(max_retries + 1):
        # Limit request bursts, including list requests and retries.
        elapsed = time.monotonic() - st.session_state.historical_last_request
        if elapsed < 1.5:
            time.sleep(1.5 - elapsed)
        st.session_state.historical_last_request = time.monotonic()
        try:
            response = session.get(BASE + path, params=params, timeout=25)
        except requests.RequestException as exc:
            if attempt < max_retries:
                time.sleep(min(4 * (attempt + 1), 12))
                continue
            return None, str(exc)
        if response.status_code == 200:
            try:
                return response.json().get('data'), None
            except ValueError:
                return None, 'Invalid JSON returned by API'
        if response.status_code == 429 and attempt < max_retries:
            try:
                retry_after = float(response.headers.get('Retry-After', '0'))
            except ValueError:
                retry_after = 0
            wait = max(retry_after, [10, 20, 40][min(attempt, 2)])
            st.info(f'API requested slower traffic (429). Waiting {wait:.0f}s before retry {attempt + 1}/{max_retries}.')
            time.sleep(min(wait, 120))
            continue
        try:
            error = response.json().get('error', {})
            if not isinstance(error, dict):
                error = {}
        except ValueError:
            error = {}
        return None, f'{response.status_code}: {error.get("code", "HTTP_ERROR")} — {error.get("message", response.text[:120])}'
    return None, 'Retries exhausted'


def fetch_matches(team_id, count, before):
    results = []
    for page in range(1, 6):
        per_page = max(20, count)
        data, error = api('/football/matches', {
            'team_id': team_id, 'status': 'finished', 'date_to': before,
            'per_page': per_page, 'page': page, 'sort': '-utc_date',
        })
        if error:
            return results[:count], error
        if not isinstance(data, list) or not data:
            break
        results.extend(data)
        if len(results) >= count or len(data) < per_page:
            break
    return results[:count], None


def side_for(match, team_id):
    return 'home' if (match.get('home_team') or {}).get('id') == team_id else 'away'


def read_stat(stats, name, side, period='all'):
    if not isinstance(stats, dict):
        return None
    for section in stats.values():
        if isinstance(section, dict) and name in section:
            value = section[name]
            if isinstance(value, dict):
                part = value.get(period)
                if isinstance(part, dict):
                    return part.get(side)
    return None


def rows_for(matches, team_id, detailed):
    rows = []
    for match in matches:
        side = side_for(match, team_id)
        other = 'away' if side == 'home' else 'home'
        mid = match.get('id')
        stats = detailed.get(mid) or {}
        score = match.get('score') or {}
        rows.append({
            'Result': ('W' if pd.to_numeric(score.get(side), errors='coerce') > pd.to_numeric(score.get(other), errors='coerce') else ('D' if score.get(side) == score.get(other) else 'L')), 
            'Date': str(match.get('utc_date', ''))[:10],
            'Opponent': (match.get(f'{other}_team') or {}).get('name', '?'),
            'H/A': 'H' if side == 'home' else 'A',
            'GF': score.get(side), 'GA': score.get(other),
            'Corners': read_stat(stats, 'corner_kicks', side),
            'Corners against': read_stat(stats, 'corner_kicks', other),
            '2H corners': read_stat(stats, 'corner_kicks', side, 'second_half'),
            'Yellows': read_stat(stats, 'yellow_cards', side),
            'Yellows against': read_stat(stats, 'yellow_cards', other),
            'Shots': read_stat(stats, 'total_shots', side),
            'Shots against': read_stat(stats, 'total_shots', other),
            'xG': read_stat(stats, 'expected_goals', side),
            'xG against': read_stat(stats, 'expected_goals', other),
            'HT xG': read_stat(stats, 'expected_goals', side, 'first_half'),
            'Match ID': mid,
            'Referee': (match.get('referee') or {}).get('name', '') if isinstance(match.get('referee'), dict) else str(match.get('referee') or ''),
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        for field in ('GF', 'GA', 'xG', 'xG against'):
            df[field] = pd.to_numeric(df[field], errors='coerce')
        df['Goals minus xG'] = df['GF'] - df['xG']
        df['xG difference'] = df['xG'] - df['xG against']
        df['xG result gap'] = (df['GF'] - df['GA']) - df['xG difference']
        def verdict(r):
            if pd.isna(r['xG difference']) or pd.isna(r['GF']) or pd.isna(r['GA']):
                return 'Insufficient evidence'
            gap = r['xG result gap']
            if gap <= -1.5:
                return 'Scoreline below chance balance'
            if gap >= 1.5:
                return 'Scoreline above chance balance'
            return 'Broadly consistent with chances'
        df['Scoreline assessment'] = df.apply(verdict, axis=1)
    return df



st.subheader('1. Automatically retrieve historical xG')
st.write('**Fixture:** Newcastle United (home) v Everton (away)')
count = st.slider('Completed matches per team', 5, 20, 20, 5)
cutoff = st.date_input('Use matches completed by', datetime.now(timezone.utc).date())
st.caption('Press once to refresh the evidence. Changing Asian lines below will not make additional API requests.')
if st.button('Fetch latest API history and calculate prices', type='primary'):
    with st.spinner('Fetching finished matches and detailed xG; rate limits may require waiting...'):
        home, he = fetch_matches(HOME_ID, count, cutoff.isoformat())
        away, ae = fetch_matches(AWAY_ID, count, cutoff.isoformat())
        if he: st.error('Newcastle match list: ' + he)
        if ae: st.error('Everton match list: ' + ae)
        details, failures = {}, []
        all_matches = {m.get('id'): m for m in home + away if m.get('id')}
        progress = st.progress(0, text='Fetching detailed xG')
        for i, mid in enumerate(all_matches):
            if mid in st.session_state.historical_stats_cache:
                details[mid] = st.session_state.historical_stats_cache[mid]
            else:
                value, err = api(f'/football/matches/{mid}/stats')
                if err: failures.append(f'{mid}: {err}')
                elif isinstance(value, dict):
                    details[mid] = value
                    st.session_state.historical_stats_cache[mid] = value
            progress.progress((i+1)/max(1,len(all_matches)), text=f'Detailed stats: {i+1}/{len(all_matches)}')
        hdf = rows_for(home, HOME_ID, details)
        adf = rows_for(away, AWAY_ID, details)
        st.session_state.asian_api_history = {'home':hdf,'away':adf,'cutoff':cutoff.isoformat(),'failures':failures}

history = st.session_state.get('asian_api_history')
if not history:
    st.info('Fetch API history to enable the model. No placeholder expected-goal values will be priced.')
    st.stop()
hdf, adf = history['home'], history['away']
home = hdf[hdf['H/A']=='H'].copy()
away = adf[adf['H/A']=='A'].copy()
for frame in (home, away):
    frame['xG'] = pd.to_numeric(frame['xG'], errors='coerce')
    frame['xG against'] = pd.to_numeric(frame['xG against'], errors='coerce')
    frame.dropna(subset=['xG','xG against'], inplace=True)
if len(home)<3 or len(away)<3:
    st.error(f'Insufficient venue-specific xG: Newcastle home {len(home)} games, Everton away {len(away)} games. Need at least three each. No prices calculated.')
    st.stop()
home_attack = home['xG'].mean()
home_defense = home['xG against'].mean()
away_attack = away['xG'].mean()
away_defense = away['xG against'].mean()
hxg = max(.05, min(6., (home_attack + away_defense)/2))
axg = max(.05, min(6., (away_attack + home_defense)/2))
st.success(f'API history loaded: {len(hdf)} Newcastle matches, {len(adf)} Everton matches. Venue-specific xG samples: {len(home)} home / {len(away)} away.')
st.write(f'**Newcastle home:** {home_attack:.2f} xG for, {home_defense:.2f} xG against')
st.write(f'**Everton away:** {away_attack:.2f} xG for, {away_defense:.2f} xG against')
col1,col2=st.columns(2)
col1.metric('Newcastle projected goals', f'{hxg:.2f}')
col2.metric('Everton projected goals', f'{axg:.2f}')
st.caption('Projection = simple average of relevant home/away attacking xG and opposing defensive xGA. This is not adjusted for opposition quality, injuries, competition, or calibration; freshness alone does not validate the odds.')
if history['failures']:
    st.warning(f"{len(history['failures'])} detailed API requests failed; the available sample was used.")
    with st.expander('Failed API requests (technical)'):
        st.write(history['failures'])
with st.expander('Historical sample and CSV export'):
    both=pd.concat([hdf.assign(Team='Newcastle'),adf.assign(Team='Everton')],ignore_index=True)
    st.dataframe(both[['Team','Date','Opponent','H/A','xG','xG against']],hide_index=True,use_container_width=True)
    st.download_button('Download API history CSV',both.to_csv(index=False).encode(),'starlizard_api_asian_history.csv','text/csv')

grid,tail=outcome_grid(hxg,axg)
if tail>1e-7:
    st.warning(f'Score grid tail: {tail:.5%}')

st.subheader('2. Choose your Asian market')
kind=st.selectbox('Market', ['Home handicap','Away handicap','Over goals','Under goals'])
lines=[i/4 for i in range(-12,13)] if 'handicap' in kind else [i/4 for i in range(2,25)]
default=0.0 if 'handicap' in kind else 2.5
line=st.selectbox('Line',lines,index=lines.index(default),format_func=lambda x:f'{x:+.2f}' if 'handicap' in kind else f'{x:.2f}')
bins,fair,w,l=price(grid,kind,line)
st.metric('Model fair decimal odds',f'{fair:.3f}')
st.write(f'**Full win:** {bins[1]:.1%} · **Half win:** {bins[.5]:.1%}')
st.write(f'**Push:** {bins[0]:.1%} · **Half loss:** {bins[-.5]:.1%} · **Full loss:** {bins[-1]:.1%}')
quote=st.number_input('Bookmaker odds (optional comparison)',1.01,1000.,1.95,.01)
ev=w*(quote-1)-l
st.metric('Model expected ROI',f'{ev:+.2%}')
st.caption('Positive model ROI does not establish a betting edge. It is conditional on the chosen expected-goals inputs and unvalidated model assumptions.')

st.subheader('3. Compact comparison')
if 'handicap' in kind:
    other='Away handicap' if kind=='Home handicap' else 'Home handicap'
    pairs=[(kind,line),(other,-line)]
else:
    other='Under goals' if kind=='Over goals' else 'Over goals'
    pairs=[(kind,line),(other,line)]
for k,v in pairs:
    b,f,_,_=price(grid,k,v)
    st.write(f'**{k} {v:+.2f}** — fair odds **{f:.3f}**')

with st.expander('Full fair-price tables and CSV export'):
    rows=[]
    for k in ('Home handicap','Away handicap','Over goals','Under goals'):
        ls=[i/4 for i in range(-12,13)] if 'handicap' in k else [i/4 for i in range(2,25)]
        for ln in ls:
            b,f,_,_=price(grid,k,ln)
            rows.append({'Market':k,'Line':ln,'Fair odds':round(f,3),
                         'Full win %':round(b[1]*100,2),'Half win %':round(b[.5]*100,2),
                         'Push %':round(b[0]*100,2),'Half loss %':round(b[-.5]*100,2),
                         'Full loss %':round(b[-1]*100,2)})
    all_prices=pd.DataFrame(rows)
    st.dataframe(all_prices[['Market','Line','Fair odds']],hide_index=True,use_container_width=True)
    st.download_button('Download full pricing CSV',all_prices.to_csv(index=False).encode(),
                       'starlizard_asian_mobile_prices.csv','text/csv')

st.caption('Next: proper team-strength model, time-aware backtesting and comparison with historical market prices. Corners require a separate distribution.')
