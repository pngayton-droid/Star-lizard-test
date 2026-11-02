"""Starlizard historical match research page. Put this file in repo/pages/."""
import os
from collections import Counter
from datetime import datetime, timezone

import pandas as pd
import requests
import streamlit as st

BASE = 'https://api.thestatsapi.com/api'
HOME_ID, AWAY_ID = 'tm_7938', 'tm_8091'
COMP_ID = 'comp_3039'

st.set_page_config(page_title='Starlizard — Historical Analysis', layout='wide')
st.title('Starlizard — Historical Analysis')
st.caption('Newcastle United v Everton • historical evidence, not betting recommendations')

key = st.secrets.get('STATS_API_KEY', os.environ.get('STATS_API_KEY', ''))
if not key:
    st.error('STATS_API_KEY is missing from Streamlit secrets. Do not paste it into chat.')
    st.stop()

session = requests.Session()
session.headers.update({'Authorization': f'Bearer {key}', 'Accept': 'application/json'})

def api(path, params=None):
    try:
        r = session.get(BASE + path, params=params, timeout=22)
        if r.status_code != 200:
            try:
                detail = r.json().get('error', {})
            except ValueError:
                detail = {}
            return None, f'{r.status_code}: {detail.get("code", "HTTP_ERROR")} — {detail.get("message", r.text[:120])}'
        return r.json().get('data'), None
    except requests.RequestException as exc:
        return None, str(exc)


def fetch_matches(team_id, count, before):
    results = []
    page = 1
    while len(results) < count and page <= 5:
        data, error = api('/football/matches', {
            'team_id': team_id, 'status': 'finished', 'date_to': before,
            'per_page': min(100, max(20, count)), 'page': page,
            'sort': '-utc_date',
        })
        if error:
            return results, error
        if not isinstance(data, list) or not data:
            break
        results.extend(data)
        if len(data) < min(100, max(20, count)):
            break
        page += 1
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
    for m in matches:
        side = side_for(m, team_id)
        opp_side = 'away' if side == 'home' else 'home'
        opponent = (m.get(f'{opp_side}_team') or {}).get('name', '?')
        score = m.get('score') or {}
        mid = m.get('id')
        stats = detailed.get(mid) or {}
        row = {
            'Date': str(m.get('utc_date', ''))[:10],
            'Opponent': opponent, 'H/A': 'H' if side == 'home' else 'A',
            'GF': score.get(side), 'GA': score.get(opp_side),
            'Corners': read_stat(stats, 'corner_kicks', side),
            'Corners against': read_stat(stats, 'corner_kicks', opp_side),
            '2H corners': read_stat(stats, 'corner_kicks', side, 'second_half'),
            'Yellows': read_stat(stats, 'yellow_cards', side),
            'Yellows against': read_stat(stats, 'yellow_cards', opp_side),
            'Shots': read_stat(stats, 'total_shots', side),
            'xG': read_stat(stats, 'expected_goals', side),
            'HT xG': read_stat(stats, 'expected_goals', side, 'first_half'),
            'Match ID': mid,
        }
        rows.append(row)
    return pd.DataFrame(rows)


def summary(df, label):
    st.subheader(label)
    if df.empty:
        st.info('No completed matches returned.')
        return
    st.dataframe(df, use_container_width=True, hide_index=True)
    cols = st.columns(4)
    for col, (name, field) in zip(cols, [('Goals for', 'GF'), ('Corners for', 'Corners'), ('Yellow cards', 'Yellows'), ('xG', 'xG')]):
        nums = pd.to_numeric(df[field], errors='coerce').dropna()
        col.metric(name, f'{nums.mean():.2f}' if len(nums) else 'N/A')
        col.caption(f'{len(nums)}/{len(df)} matches with data')

st.info('First run: use 5 matches per team to check data coverage and conserve API quota. Increase to 20 after verifying.')
count = st.slider('Completed matches per team', min_value=5, max_value=20, value=5, step=5)
cutoff = st.date_input('Results on or before', value=datetime.now(timezone.utc).date())
include_details = st.checkbox('Fetch detailed stats for every match (extra API requests)', value=True)

if st.button('Analyse historical matches', type='primary'):
    with st.spinner('Retrieving historical records from TheStatsAPI...'):
        coverage, coverage_error = api('/coverage/leagues/' + COMP_ID)
        home, h_err = fetch_matches(HOME_ID, count, cutoff.isoformat())
        away, a_err = fetch_matches(AWAY_ID, count, cutoff.isoformat())
        if h_err:
            st.error('Newcastle match list: ' + h_err)
        if a_err:
            st.error('Everton match list: ' + a_err)
        details, failures = {}, []
        if include_details:
            all_matches = {m.get('id'): m for m in home + away if m.get('id')}
            for mid in all_matches:
                result, error = api(f'/football/matches/{mid}/stats')
                if error:
                    failures.append((mid, error))
                else:
                    details[mid] = result
        st.session_state['historical_result'] = {
            'coverage': coverage, 'coverage_error': coverage_error,
            'home': rows_for(home, HOME_ID, details),
            'away': rows_for(away, AWAY_ID, details),
            'failures': failures,
            'requests_note': f'{len(home)} Newcastle matches, {len(away)} Everton matches, {len(details)} detailed stats responses',
        }

if 'historical_result' in st.session_state:
    r = st.session_state['historical_result']
    st.success(r['requests_note'])
    if r['coverage_error']:
        st.warning('Coverage lookup: ' + r['coverage_error'])
    elif r['coverage']:
        with st.expander('Premier League historical coverage'):
            st.json(r['coverage'])
    summary(r['home'], 'Newcastle United — recent matches')
    summary(r['away'], 'Everton — recent matches')
    if r['failures']:
        with st.expander(f'{len(r["failures"])} matches without detailed stats'):
            st.dataframe(pd.DataFrame(r['failures'], columns=['Match ID', 'API response']), hide_index=True)
    combined = pd.concat([r['home'].assign(Team='Newcastle'), r['away'].assign(Team='Everton')], ignore_index=True)
    st.download_button('Download historical analysis CSV', combined.to_csv(index=False).encode('utf-8'),
                       file_name='starlizard_historical_analysis.csv', mime='text/csv')
    st.caption('Averages use only matches with available stats. Missing statistics are never counted as zero. This is descriptive research, not fair-price estimation.')
