"""Pro Star Lizard historical analysis: paced API calls and recoverable results."""
import os
import time
from datetime import datetime, timezone

import pandas as pd
import requests
import streamlit as st

BASE = 'https://api.thestatsapi.com/api'
HOME_ID, AWAY_ID = 'tm_7938', 'tm_8091'

st.set_page_config(page_title='Starlizard — Historical Analysis', layout='wide')
st.title('Starlizard — Historical Analysis')
st.caption('Newcastle United v Everton | historical evidence, not betting recommendations')

key = st.secrets.get('STATS_API_KEY', os.environ.get('STATS_API_KEY', ''))
if not key:
    st.error('STATS_API_KEY is missing from Streamlit secrets. Do not paste it into chat.')
    st.stop()

session = requests.Session()
session.headers.update({'Authorization': f'Bearer {key}', 'Accept': 'application/json'})

# Keep successful detailed responses during reruns in the same Streamlit session.
if 'historical_stats_cache' not in st.session_state:
    st.session_state.historical_stats_cache = {}
if 'historical_last_request' not in st.session_state:
    st.session_state.historical_last_request = 0.0


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
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        for field in ('GF', 'GA', 'xG', 'xG against'):
            df[field] = pd.to_numeric(df[field], errors='coerce')
        df['Goals minus xG'] = df['GF'] - df['xG']
        df['xG difference'] = df['xG'] - df['xG against']
    return df


def summary(df, label):
    st.subheader(label)
    if df.empty:
        st.info('No completed matches returned.')
        return
    st.dataframe(df, use_container_width=True, hide_index=True)
    cols = st.columns(4)
    for col, (name, field) in zip(cols, [
        ('Goals for', 'GF'), ('Corners for', 'Corners'),
        ('Yellow cards', 'Yellows'), ('xG', 'xG'),
    ]):
        values = pd.to_numeric(df[field], errors='coerce').dropna()
        col.metric(name, f'{values.mean():.2f}' if len(values) else 'N/A')
        col.caption(f'{len(values)}/{len(df)} matches with data')
    with st.expander('Performance vs underlying xG (descriptive)'):
        sample = df.dropna(subset=['GF', 'GA', 'xG', 'xG against'])
        st.write(f'{len(sample)} matches with both actual and expected goals.')
        if len(sample):
            st.write(f'Goals minus xG: {sample["Goals minus xG"].sum():+.2f} across those matches.')
            st.write(f'Average xG difference: {sample["xG difference"].mean():+.2f} per match.')
            st.caption('Finishing above/below xG is not proof of luck or a prediction of future regression.')

st.info('Requests are paced and HTTP 429 responses are retried. Successful detailed stats are reused within this app session.')
count = st.slider('Completed matches per team', min_value=5, max_value=20, value=20, step=5)
cutoff = st.date_input('Results on or before', value=datetime.now(timezone.utc).date())
include_details = st.checkbox('Fetch detailed stats for every match (extra API requests)', value=True)

if st.button('Analyse historical matches', type='primary'):
    with st.spinner('Retrieving historical records from TheStatsAPI...'):
        home, h_err = fetch_matches(HOME_ID, count, cutoff.isoformat())
        away, a_err = fetch_matches(AWAY_ID, count, cutoff.isoformat())
        if h_err:
            st.error('Newcastle match list: ' + h_err)
        if a_err:
            st.error('Everton match list: ' + a_err)
        details, failures = {}, []
        all_matches = {m.get('id'): m for m in home + away if m.get('id')}
        if include_details:
            progress = st.progress(0, text='Retrieving detailed match stats...')
            for i, mid in enumerate(all_matches):
                if mid in st.session_state.historical_stats_cache:
                    details[mid] = st.session_state.historical_stats_cache[mid]
                else:
                    result, error = api(f'/football/matches/{mid}/stats')
                    if error:
                        failures.append((mid, error))
                    elif result is not None:
                        details[mid] = result
                        st.session_state.historical_stats_cache[mid] = result
                    else:
                        failures.append((mid, 'Empty stats response'))
                progress.progress((i + 1) / len(all_matches), text=f'Detailed stats: {i + 1}/{len(all_matches)} matches checked')
            progress.empty()
        st.session_state['historical_result'] = {
            'home': rows_for(home, HOME_ID, details),
            'away': rows_for(away, AWAY_ID, details),
            'failures': failures,
            'note': f'{len(home)} Newcastle matches, {len(away)} Everton matches, {len(details)} detailed stats responses',
        }

if 'historical_result' in st.session_state:
    result = st.session_state.historical_result
    st.success(result['note'])
    summary(result['home'], 'Newcastle United — recent matches')
    summary(result['away'], 'Everton — recent matches')
    if result['failures']:
        st.warning(f'{len(result["failures"])} detailed stats requests did not succeed. See responses below.')
        with st.expander('Detailed API errors', expanded=True):
            st.dataframe(pd.DataFrame(result['failures'], columns=['Match ID', 'API response']), hide_index=True)
    combined = pd.concat([
        result['home'].assign(Team='Newcastle'),
        result['away'].assign(Team='Everton'),
    ], ignore_index=True)
    st.download_button('Download historical analysis CSV', combined.to_csv(index=False).encode('utf-8'),
                       file_name='starlizard_historical_analysis.csv', mime='text/csv')
    st.caption('Missing statistics are not treated as zero. Descriptive analysis only; not fair-price estimation.')
