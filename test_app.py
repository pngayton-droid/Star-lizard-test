"""Separate experimental pricing UI; does not alter existing scanner."""
import datetime
import pandas as pd
import streamlit as st
from model import load, Model
from score_pricer import price, edge

st.set_page_config(page_title='Football pricing lab', layout='wide')
st.title('Football pricing lab — experimental')
st.warning('Research tool only. Prices are model estimates, not verified market edges. No automatic bets.')

@st.cache_data(show_spinner='Loading historical matches…')
def historical(path):
    return load(path)

@st.cache_resource(show_spinner='Training historical team ratings…')
def fit(path, asof):
    data=historical(path)
    data=data[data.date < pd.Timestamp(asof)]
    m=Model()
    for date, group in data.groupby('date', sort=True):
        for r in group.itertuples(index=False):
            m.update(str(r.Div),str(r.HomeTeam),str(r.AwayTeam),int(r.FTHG),int(r.FTAG))
    return m, int(len(data))

st.caption('Data available only through the selected as-of date. Historical score results are never used to price matches on or before that date.')
path=st.text_input('Historical CSV path', 'https://raw.githubusercontent.com/pngayton-droid/football-value-scanner/main/football_merged_32653.csv')
asof=st.date_input('Price matches as of (training strictly before this date)',value=datetime.date(2026,10,30))
try:
    m, n=fit(path,asof.isoformat())
except Exception as ex:
    st.error(f'Could not load historical data: {ex}')
    st.stop()
st.caption(f'{n:,} prior matches used to build ratings. Bookmaker odds are not used to calculate the model price.')
leagues=sorted({key for key in m.league if len(m.league[key]['hg'])>=60})
if not leagues:
    st.error('Insufficient historical league data'); st.stop()
league=st.selectbox('League',leagues)
teams=sorted({team for div,team in m.team if div==league})
if len(teams)<2: st.stop()
a,b=st.columns(2)
with a: home=st.selectbox('Home team',teams,index=0)
with b: away=st.selectbox('Away team',teams,index=min(1,len(teams)-1))
if home==away:
    st.warning('Choose two different teams');st.stop()
pred=m.predict(league,home,away)
if pred is None:
    st.warning('Not enough team history for this fixture');st.stop()
lh,la,_=pred
st.write(f'Estimated full-match goals: **{home} {lh:.2f} — {la:.2f} {away}**')
st.subheader('Full-time fair prices')
res=price(lh,la)
labels={'home':'Home win','draw':'Draw','away':'Away win','over25':'Over 2.5','under25':'Under 2.5','btts_yes':'BTTS Yes','btts_no':'BTTS No'}
rows=[{'Market':labels[k],'Probability':f'{p:.1%}','Fair decimal':round(res['fair_odds'][k],2)} for k,p in res['probabilities'].items()]
st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
st.subheader('Correct-score prices')
scores=sorted(res['scores'].items(),key=lambda x:x[1],reverse=True)[:15]
st.dataframe(pd.DataFrame([{'Score':s,'Probability':f'{p:.2%}','Fair decimal':round(1/p,2)} for s,p in scores]),hide_index=True,use_container_width=True)
st.subheader('Compare with an actual market quote')
market=st.selectbox('Market',list(labels),format_func=lambda k:labels[k])
col1,col2=st.columns(2)
with col1: odds=st.number_input('Available decimal odds',min_value=1.01,max_value=1000.,value=2.00,step=.05)
with col2: commission=st.number_input('Exchange commission (%)',min_value=0.,max_value=30.,value=0.,step=.5)
p=res['probabilities'][market]
ev=edge(p,odds,commission/100)
st.metric('Estimated expected return per £1 staked',f'{ev:+.1%}')
st.caption('This is theoretical EV from an unvalidated model. It excludes slippage and price availability; a positive value is NOT proof of value.')
st.subheader('In-play sandbox (unvalidated)')
st.caption('Simple time-scaled Poisson only. It does NOT use live xG, red cards, substitutions or score-dependent goal rates.')
c1,c2,c3=st.columns(3)
with c1: minute=st.slider('Minute',0,90,45)
with c2: sh=st.number_input('Current home goals',0,15,0)
with c3: sa=st.number_input('Current away goals',0,15,0)
live=price(lh,la,sh,sa,(90-minute)/90)
st.dataframe(pd.DataFrame([{'Market':labels[k],'Probability':f'{p:.1%}','Fair decimal':round(live['fair_odds'][k],2) if live['fair_odds'][k] else None} for k,p in live['probabilities'].items()]),hide_index=True,use_container_width=True)


st.divider()
st.header('TheStatsAPI — fixture and odds connection (experimental)')
st.caption('Live data comes from TheStatsAPI; no automated betting or model-to-team matching. Fixture/odds requests are cached for 5 minutes.')

@st.cache_data(ttl=300, show_spinner='Contacting TheStatsAPI…')
def api_get(endpoint, params, secret):
    import json
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError
    url = 'https://api.thestatsapi.com/api' + endpoint
    if params:
        url += '?' + urlencode(params)
    req = Request(url, headers={'Authorization': 'Bearer ' + secret, 'Accept': 'application/json'})
    try:
        with urlopen(req, timeout=18) as response:
            return json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f'TheStatsAPI returned HTTP {exc.code}. Check subscription, key and coverage.') from None
    except URLError:
        raise RuntimeError('Could not connect to TheStatsAPI.') from None

api_key = st.secrets.get('STATS_API_KEY', '')
if not api_key:
    st.info('Set STATS_API_KEY in this app’s Streamlit Secrets to enable API requests.')
else:
    st.success('API key found in Streamlit Secrets (not displayed).')
    comp = st.text_input('Competition ID', 'comp_3039', help='Example ID for Premier League from provider documentation.')
    date1 = st.date_input('Fixtures from', value=datetime.date.today(), key='api_from')
    date2 = st.date_input('Fixtures to', value=datetime.date.today() + datetime.timedelta(days=2), key='api_to')
    if st.button('Fetch fixtures from TheStatsAPI'):
        if date2 < date1:
            st.error('End date must not be earlier than start date.')
        else:
            try:
                result = api_get('/football/matches', {'competition_id':comp, 'date_from':date1.isoformat(), 'date_to':date2.isoformat(), 'per_page':50}, api_key)
                items = result.get('data', [])
                if not isinstance(items, list):
                    raise ValueError('Unexpected match data format')
                st.session_state['api_matches'] = items
                st.session_state['api_comp'] = comp
                st.caption(f'{len(items)} fixtures returned on first page. More pages may exist.')
            except Exception as exc:
                st.error(str(exc))
    matches = st.session_state.get('api_matches', [])
    if matches:
        choices = {}
        for match in matches:
            mid = str(match.get('id',''))
            if not mid.startswith('mt_'):
                continue
            h = match.get('home_team') or {}
            a = match.get('away_team') or {}
            label = f"{match.get('utc_date','')} | {h.get('name','?')} vs {a.get('name','?')} | {match.get('status','')} | {mid}"
            choices[label] = mid
        if choices:
            selected = st.selectbox('Select an API fixture', list(choices))
            if st.button('Fetch bookmaker odds for this fixture'):
                try:
                    result = api_get('/football/matches/' + choices[selected] + '/odds', {}, api_key)
                    st.session_state['api_odds'] = result.get('data', {})
                    st.session_state['api_odds_match'] = choices[selected]
                except Exception as exc:
                    st.error(str(exc))
    if st.session_state.get('api_odds') is not None and st.session_state.get('api_odds_match'):
        st.subheader('Provider odds response')
        st.caption('Inspect bookmaker market structure here. Automatic odds comparisons will be enabled only after confirming the returned format and mapping teams correctly.')
        st.json(st.session_state['api_odds'], expanded=False)


# Automatic parsing of the confirmed provider match_odds schema.
# Team-to-model mapping remains explicit: no silent guesses.
if st.session_state.get('api_odds') and st.session_state.get('api_odds_match'):
    st.subheader('Bookmaker 1X2 prices')
    st.caption('Odds for match ID: ' + str(st.session_state['api_odds_match']))
    odds_payload = st.session_state['api_odds']
    bookmaker_rows = []
    for bk in odds_payload.get('bookmakers', []):
        if not isinstance(bk, dict):
            continue
        market_prices = bk.get('markets', {}).get('match_odds', {})
        row = {'Bookmaker': bk.get('bookmaker', 'Unknown')}
        valid = True
        for outcome in ('home', 'draw', 'away'):
            selection = market_prices.get(outcome, {})
            if not isinstance(selection, dict):
                valid = False
                break
            for quote_type in ('opening', 'last_seen'):
                try:
                    quote = float(selection.get(quote_type))
                    if not (1.0 < quote < 10000.0):
                        raise ValueError('Invalid quote')
                    row[f'{outcome}_{quote_type}'] = quote
                except (TypeError, ValueError):
                    row[f'{outcome}_{quote_type}'] = None
        if valid:
            prices = [row.get(f'{x}_last_seen') for x in ('home', 'draw', 'away')]
            row['Overround %'] = round(100 * (sum(1 / x for x in prices) - 1), 2) if all(prices) else None
            bookmaker_rows.append(row)
    if bookmaker_rows:
        st.dataframe(pd.DataFrame(bookmaker_rows), hide_index=True, use_container_width=True)
        st.caption('Last seen means last recorded by the provider, not guaranteed live or currently available.')
        st.subheader('Compare 1X2 prices to the model (manual fixture matching)')
        st.warning('Confirm the selected league and both teams are the SAME fixture as the API match. Do not compare prices from different matches.')
        compare_league = st.selectbox('Model league for API fixture', leagues, key='api_compare_league')
        compare_teams = sorted({team for div, team in m.team if div == compare_league})
        if len(compare_teams) >= 2:
            model_home = st.selectbox('API home team in historical database', compare_teams, key='api_compare_home')
            model_away = st.selectbox('API away team in historical database', compare_teams, index=1, key='api_compare_away')
            selected_bk = st.selectbox('Bookmaker to compare', [row['Bookmaker'] for row in bookmaker_rows], key='api_compare_bookmaker')
            quote_kind = st.radio('Which prices?', ['last_seen', 'opening'], horizontal=True, key='api_quote_kind')
            confirmed = st.checkbox('I have verified the home and away teams match the selected API fixture', key='api_teams_confirmed')
            if confirmed:
                if model_home == model_away:
                    st.error('Home and away cannot be the same team.')
                else:
                    match_pred = m.predict(compare_league, model_home, model_away)
                    if match_pred is None:
                        st.error('Not enough historical matches for these teams.')
                    else:
                        match_prices = price(match_pred[0], match_pred[1])
                        selected_row = next(row for row in bookmaker_rows if row['Bookmaker'] == selected_bk)
                        comparison = []
                        for outcome, name in [('home', 'Home win'), ('draw', 'Draw'), ('away', 'Away win')]:
                            offered = selected_row.get(f'{outcome}_{quote_kind}')
                            probability = match_prices['probabilities'][outcome]
                            comparison.append({
                                'Outcome': name,
                                'Model probability': f'{probability:.1%}',
                                'Model fair odds': round(1 / probability, 2),
                                'Bookmaker odds': offered,
                                'Model EV %': round(100 * (probability * offered - 1), 2) if offered else None,
                            })
                        st.dataframe(pd.DataFrame(comparison), hide_index=True, use_container_width=True)
                        st.caption('Unvalidated theoretical expected values, not betting recommendations. Bookmaker prices may be stale. Historical data may not include current-season form.')
    else:
        st.info('No valid 1X2 prices found in this odds response.')

# Historical Situation Analyser — incremental, quota-conscious importer.
st.divider()
st.header('Historical Situation Analyser — improved importer')
st.caption('Import completed matches in small batches, then filter historical outcomes. Descriptive historical frequencies are not validated predictive probabilities.')

import io
import math
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
import json
import base64

@st.cache_data(ttl=86400, show_spinner=False)
def historical_api_get(endpoint, parameters, secret):
    """Cache successful responses, pause between calls and retry short-term 429s."""
    url = 'https://api.thestatsapi.com/api' + endpoint
    if parameters:
        url += '?' + urlencode(parameters)
    request = Request(url, headers={'Authorization': 'Bearer ' + secret, 'Accept': 'application/json'})
    for attempt in range(3):
        time.sleep(1.2)
        try:
            with urlopen(request, timeout=25) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code == 429:
                if attempt == 2:
                    raise RuntimeError('HTTP 429 after retries. Stop importing and check rate limits or account restrictions.') from None
                retry_after = exc.headers.get('Retry-After', '')
                try:
                    wait = min(30, max(2, float(retry_after)))
                except (ValueError, TypeError):
                    wait = [5, 12][attempt]
                time.sleep(wait)
                continue
            raise RuntimeError(f'TheStatsAPI returned HTTP {exc.code} on {endpoint}.') from None
        except URLError:
            raise RuntimeError('Could not connect to TheStatsAPI.') from None

def nested(obj, *keys):
    for key in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj

def numeric(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None

def extract_1x2(odds):
    """Keep opening and last-seen snapshots distinct; never treat latter as closing."""
    payload = odds.get('data', odds) if isinstance(odds, dict) else {}
    bookmakers = payload.get('bookmakers', []) if isinstance(payload, dict) else []
    if not isinstance(bookmakers, list):
        bookmakers = []
    bookmakers = sorted((b for b in bookmakers if isinstance(b, dict)),
                         key=lambda b: 0 if 'bet365' in str(b.get('bookmaker', '')).lower() else 1)
    result = {'opening_home': None, 'opening_draw': None, 'opening_away': None,
              'last_seen_home': None, 'last_seen_draw': None, 'last_seen_away': None,
              'opening_bookmaker': None, 'last_seen_bookmaker': None,
              'bookmaker': None, 'odds_status': 'No bookmaker data'}
    if bookmakers:
        result['odds_status'] = 'Bookmakers returned; no complete 1X2 snapshot'
    for kind in ('opening', 'last_seen'):
        for bk in bookmakers:
            selections = nested(bk, 'markets', 'match_odds') or {}
            values = [numeric(nested(selections, k, kind)) for k in ('home', 'draw', 'away')]
            if all(v is not None and v > 1 for v in values):
                result.update(dict(zip((kind + '_home', kind + '_draw', kind + '_away'), values)))
                result[kind + '_bookmaker'] = str(bk.get('bookmaker', 'Unknown'))
                break
    result['bookmaker'] = result['opening_bookmaker'] or result['last_seen_bookmaker']
    has_open = result['opening_bookmaker'] is not None
    has_last = result['last_seen_bookmaker'] is not None
    if has_open and has_last:
        result['odds_status'] = 'Opening and last_seen 1X2 found'
    elif has_open:
        result['odds_status'] = 'Opening 1X2 only'
    elif has_last:
        result['odds_status'] = 'Last_seen 1X2 only (timing unverified)'
    return result

def parse_historical_match(summary, detail, stats, odds):
    match = detail.get('data', detail)
    match_id = str(summary.get('id', ''))
    score = match.get('score') or {}
    hth = numeric(score.get('half_time_home'))
    hta = numeric(score.get('half_time_away'))
    fth = numeric(score.get('home'))
    fta = numeric(score.get('away'))
    stats_data = stats.get('data', stats)
    xgh = numeric(nested(stats_data, 'overview', 'expected_goals', 'first_half', 'home'))
    xga = numeric(nested(stats_data, 'overview', 'expected_goals', 'first_half', 'away'))
    home_team = match.get('home_team') or summary.get('home_team') or {}
    away_team = match.get('away_team') or summary.get('away_team') or {}
    return {
        'match_id': match_id,
        'date': match.get('utc_date') or summary.get('utc_date'),
        'home': home_team.get('name', '?') if isinstance(home_team, dict) else str(home_team),
        'away': away_team.get('name', '?') if isinstance(away_team, dict) else str(away_team),
        'HT_home': hth, 'HT_away': hta, 'FT_home': fth, 'FT_away': fta,
        'HT_xG_home': xgh, 'HT_xG_away': xga,
        **extract_1x2(odds),
    }

# Optional durable storage: a separate file committed to the Starlizard repo.
# A Streamlit session/local file is NOT durable storage on Community Cloud.
HIST_REPO = 'pngayton-droid/Star-lizard-test'
HIST_REPO_PATH = 'data/historical_matches.csv'

def github_history_read():
    url = f'https://raw.githubusercontent.com/{HIST_REPO}/main/{HIST_REPO_PATH}'
    with urlopen(Request(url, headers={'Accept': 'text/csv'}), timeout=20) as resp:
        return pd.read_csv(io.BytesIO(resp.read()))

def github_history_save(rows, token):
    """Merge remote and session by match ID, then commit with optimistic SHA lock."""
    endpoint = f'https://api.github.com/repos/{HIST_REPO}/contents/{HIST_REPO_PATH}'
    headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
               'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'Starlizard-History'}
    sha = None
    merged = {}
    try:
        with urlopen(Request(endpoint, headers=headers), timeout=20) as resp:
            existing = json.load(resp)
        sha = existing['sha']
        raw = base64.b64decode(existing['content'])
        for record in pd.read_csv(io.BytesIO(raw)).to_dict('records'):
            mid = str(record.get('match_id', ''))
            if mid.startswith('mt_'):
                merged[mid] = record
    except HTTPError as exc:
        if exc.code != 404:
            raise RuntimeError(f'GitHub read failed (HTTP {exc.code})') from None
    # Preserve existing nonempty fields when new session has missing values.
    for mid, row in rows.items():
        old = merged.get(mid, {})
        new = dict(old)
        for k, v in row.items():
            if v is not None and not (isinstance(v, float) and pd.isna(v)) and str(v).strip() != '':
                new[k] = v
        merged[mid] = new
    csv_bytes = pd.DataFrame(merged.values()).to_csv(index=False).encode('utf-8')
    payload = {'message': 'Update Starlizard historical research dataset',
               'content': base64.b64encode(csv_bytes).decode('ascii'), 'branch': 'main'}
    if sha:
        payload['sha'] = sha
    req = Request(endpoint, data=json.dumps(payload).encode(), headers={**headers, 'Content-Type': 'application/json'}, method='PUT')
    try:
        with urlopen(req, timeout=30) as resp:
            json.load(resp)
    except HTTPError as exc:
        raise RuntimeError(f'GitHub save failed (HTTP {exc.code}). Existing data was not overwritten; check permissions or concurrent changes.') from None
    return len(merged)

if not api_key:
    st.info('The Historical Situation Analyser uses the STATS_API_KEY already configured in Streamlit Secrets.')
else:
    st.markdown('**Step 1 — Import historical matches**')
    hist_comp = st.text_input('Historical competition ID', 'comp_3039', key='hist_comp')
    hist_season = st.text_input('Historical season ID (2025/26 Premier League)', 'sn_6125938', key='hist_season')
    batch_size = st.select_slider('Matches per import batch', options=[2, 5, 10], value=5, key='hist_batch')
    st.caption('Each match can require up to 3 detail requests. Requests are spaced out and temporary HTTP 429 errors retried. Import only when needed; the API may count retries against quota.')
    if 'historical_rows' not in st.session_state:
        st.session_state.historical_rows = {}
    if 'historical_page' not in st.session_state:
        st.session_state.historical_page = 1
    if 'historical_context' not in st.session_state:
        st.session_state.historical_context = None
    context = (hist_comp.strip(), hist_season.strip())
    if st.session_state.historical_context != context:
        st.session_state.historical_rows = {}
        st.session_state.historical_page = 1
        st.session_state.historical_context = context
    st.markdown('**Durable database — Starlizard GitHub repository**')
    st.caption('Optional: save the historical CSV to data/historical_matches.csv in Star-lizard-test. This does not change the original football-value-scanner. Streamlit session data alone is temporary.')
    if st.button('Load saved database from Starlizard GitHub', key='hist_github_load'):
        try:
            remote = github_history_read()
            if 'match_id' not in remote.columns or not {'HT_home','HT_away','FT_home','FT_away'}.issubset(remote.columns):
                raise ValueError('Saved database is missing required columns.')
            for rec in remote.to_dict('records'):
                mid = str(rec.get('match_id', ''))
                if mid.startswith('mt_'):
                    st.session_state.historical_rows[mid] = {k: (None if pd.isna(v) else v) for k,v in rec.items()}
            st.success(f'Loaded {len(st.session_state.historical_rows)} matches; no StatsAPI requests used.')
        except HTTPError as exc:
            if exc.code == 404:
                st.info('No database has been saved to this repository yet. Restore your CSV below first.')
            else:
                st.error(f'GitHub read returned HTTP {exc.code}.')
        except Exception as exc:
            st.error('Could not load GitHub database: ' + str(exc))
    try:
        github_token = st.secrets.get('STARLIZARD_GITHUB_TOKEN', '')
    except Exception:
        github_token = ''
    if github_token:
        if st.button('Save / merge database permanently to Starlizard GitHub', key='hist_github_save'):
            if not st.session_state.historical_rows:
                st.warning('Load or import some matches first.')
            else:
                try:
                    count = github_history_save(st.session_state.historical_rows, github_token)
                    st.success(f'Saved {count} unique matches to Starlizard GitHub. Your CSV backup is still recommended.')
                except Exception as exc:
                    st.error(str(exc))
    else:
        st.info('Permanent GitHub saving is not yet enabled. To enable it later, add STARLIZARD_GITHUB_TOKEN to Streamlit Secrets with access only to the Starlizard repository. Until then, use CSV backups.')
    restore = st.file_uploader('Restore historical CSV (Android-compatible: choose any file type)', type=None, key='hist_restore')
    st.caption('Android may grey out CSV files when the picker filters by type. This upload accepts any file; the app checks its CSV columns before restoring.')
    if restore is not None and st.button('Load CSV into analyser', key='hist_restore_button'):
        try:
            if not restore.name.lower().endswith('.csv'):
                raise ValueError('Please choose a .csv file, not a Python or PDF file.')
            restored = pd.read_csv(restore)
            needed = {'match_id', 'HT_home', 'HT_away', 'FT_home', 'FT_away'}
            if not needed.issubset(restored.columns):
                raise ValueError('This CSV is missing required match columns.')
            for _, record in restored.iterrows():
                mid = str(record['match_id'])
                if mid.startswith('mt_'):
                    st.session_state.historical_rows[mid] = {k: (None if pd.isna(v) else v) for k, v in record.to_dict().items()}
            st.success(f'Restored {len(st.session_state.historical_rows)} unique matches. No API calls used.')
        except Exception as ex:
            st.error('Could not restore CSV: ' + str(ex))
    if st.button('Import next batch of finished matches', key='hist_import'):
        if not all(context):
            st.error('Please enter both the competition and season IDs.')
        else:
            try:
                # Pages of 10 allow gradual import and avoid accidental large downloads.
                page = st.session_state.historical_page
                listing = historical_api_get('/football/matches', {
                    'competition_id': context[0], 'season_id': context[1],
                    'status': 'finished', 'per_page': batch_size, 'page': page
                }, api_key)
                summaries = listing.get('data', [])
                if not isinstance(summaries, list):
                    raise ValueError('Unexpected match listing format')
                added = 0
                errors = []
                for summary in summaries:
                    mid = str(summary.get('id', ''))
                    if not mid.startswith('mt_') or mid in st.session_state.historical_rows:
                        continue
                    try:
                        detail = historical_api_get('/football/matches/' + mid, {}, api_key)
                        stats = historical_api_get('/football/matches/' + mid + '/stats', {}, api_key)
                        odds = historical_api_get('/football/matches/' + mid + '/odds', {}, api_key)
                        row = parse_historical_match(summary, detail, stats, odds)
                        st.session_state.historical_rows[mid] = row
                        added += 1
                    except Exception as ex:
                        errors.append(mid + ': ' + str(ex))
                # Advance only if every returned match was processed, to permit retry.
                if not errors:
                    st.session_state.historical_page += 1
                st.success(f'Imported {added} matches. Total saved in this browser session: {len(st.session_state.historical_rows)}.')
                if errors:
                    st.warning('Some matches could not be imported. The page will be retried. ' + ' | '.join(errors[:2]))
                    if any('429' in e for e in errors):
                        st.error('Rate limit reached: stop importing for now. Download your CSV to preserve the successful records.')
                if not summaries:
                    st.info('No matches returned on this page. This season may be exhausted or not covered.')
            except Exception as ex:
                st.error('Historical import failed: ' + str(ex))
    # Diagnose one saved historical match without re-fetching its scores or stats.
    # This deliberately makes at most one odds endpoint call per button press.
    if st.session_state.historical_rows:
        st.markdown('**Historical bookmaker odds — inspect and repair**')
        st.caption('Use a saved match to inspect its bookmaker response and attempt an odds-only repair. No match-score or xG requests are made.')
        saved_ids = sorted(st.session_state.historical_rows)
        odds_match_id = st.selectbox('Saved match to check', saved_ids, format_func=lambda mid: (
            f"{st.session_state.historical_rows[mid].get('home', '?')} v {st.session_state.historical_rows[mid].get('away', '?')} — {mid}"
        ), key='hist_odds_inspect_match')
        if st.button('Inspect and repair odds for this one match', key='hist_odds_inspect'):
            try:
                odds_response = historical_api_get('/football/matches/' + odds_match_id + '/odds', {}, api_key)
                payload = odds_response.get('data', odds_response) if isinstance(odds_response, dict) else odds_response
                st.session_state['hist_odds_inspection'] = {'id': odds_match_id, 'payload': payload}
                if isinstance(payload, dict):
                    bks = payload.get('bookmakers', [])
                    if not isinstance(bks, list):
                        bks = []
                    updated = extract_1x2(payload)
                    row = st.session_state.historical_rows[odds_match_id]
                    row.update(updated)
                    if updated['opening_bookmaker'] or updated['last_seen_bookmaker']:
                        st.success('Saved available 1X2 snapshots. Download a fresh CSV backup below.')
                    else:
                        st.warning('No complete 1X2 snapshot found. Inspect the response below.')
                else:
                    st.warning('Unexpected odds response format. Inspect the response below.')
            except Exception as exc:
                st.error('Odds inspection failed: ' + str(exc))
        inspected = st.session_state.get('hist_odds_inspection')
        if inspected:
            st.caption('Odds response structure for ' + inspected['id'] + '. Avoid sharing anything containing credentials; this view should contain only bookmaker odds.')
            payload = inspected['payload']
            if isinstance(payload, dict):
                st.write('Top-level fields:', ', '.join(map(str, payload.keys())))
                bookmakers = payload.get('bookmakers', [])
                st.write('Bookmakers:', len(bookmakers) if isinstance(bookmakers, list) else 'Not a list')
                if isinstance(bookmakers, list) and bookmakers:
                    sample = next((b for b in bookmakers if isinstance(b, dict)), None)
                    if sample:
                        st.json(sample, expanded=False)
                else:
                    st.json(payload, expanded=False)
            else:
                st.json(payload, expanded=False)
    if st.session_state.historical_rows:
        hist_df = pd.DataFrame(st.session_state.historical_rows.values())
        st.download_button('Download imported historical matches (CSV)', hist_df.to_csv(index=False).encode('utf-8'), 'starlizard_historical_matches.csv', 'text/csv', key='hist_download')
        st.caption('Download a CSV backup after each import. Streamlit sessions are temporary; permanent GitHub saving is available only when its separate token is configured.')
        st.markdown('**Step 2 — Explore historical situations**')
        total = len(hist_df)
        complete_scores = hist_df[['HT_home', 'HT_away', 'FT_home', 'FT_away']].notna().all(axis=1).sum()
        complete_xg = hist_df[['HT_xG_home', 'HT_xG_away']].notna().all(axis=1).sum()
        for field in ('opening_home','opening_draw','opening_away','last_seen_home','last_seen_draw','last_seen_away'):
            if field not in hist_df.columns:
                hist_df[field] = float('nan')
            hist_df[field] = pd.to_numeric(hist_df[field], errors='coerce')
        complete_opening = int(hist_df[['opening_home', 'opening_draw', 'opening_away']].notna().all(axis=1).sum())
        complete_last = int(hist_df[['last_seen_home', 'last_seen_draw', 'last_seen_away']].notna().all(axis=1).sum())
        st.write(f'Imported **{total}** | Complete HT/FT scores **{complete_scores}** | Both HT xG values **{complete_xg}** | Complete opening 1X2 **{complete_opening}** | Complete last_seen 1X2 **{complete_last}**')
        st.caption('Last_seen is the last price recorded by the provider, NOT verified pre-match or closing odds. Do not use it as a pre-match backtest price until its timestamp is verified.')
        if 'odds_status' in hist_df.columns:
            st.dataframe(hist_df['odds_status'].fillna('Previously imported / unknown').value_counts().rename_axis('Status').reset_index(name='Matches'), hide_index=True, use_container_width=True)
        ht_score = st.selectbox('Halftime score (home–away)', ['Any', '0–0', '1–0', '0–1', '1–1', '2–0', '0–2', '2–1', '1–2'], key='hist_score')
        side = st.selectbox('Pre-match team to filter by odds', ['Any', 'Home', 'Away', 'Favourite'], key='hist_side')
        odds_kind = st.selectbox('Odds snapshot for historical filter', ['opening', 'last_seen'], key='hist_odds_kind')
        if odds_kind == 'last_seen':
            st.warning('Research-only: last_seen timing is unverified; results must not be treated as a pre-match odds backtest.')
        min_odds, max_odds = st.slider('Selected decimal odds range', 1.01, 15.0, (1.50, 5.00), 0.01, key='hist_odds')
        xg_filter = st.selectbox('First-half xG filter', ['No xG filter', 'Home xG at least', 'Away xG at least', 'Trailing team xG at least'], key='hist_xg_filter')
        min_xg = st.number_input('Minimum first-half xG', 0.0, 10.0, 0.20, 0.05, key='hist_min_xg') if xg_filter != 'No xG filter' else None
        filtered = hist_df.dropna(subset=['HT_home', 'HT_away', 'FT_home', 'FT_away']).copy()
        if ht_score != 'Any':
            h, a = [int(x) for x in ht_score.split('–')]
            filtered = filtered[(filtered.HT_home == h) & (filtered.HT_away == a)]
        if side != 'Any':
            filtered = filtered.dropna(subset=[odds_kind + '_home', odds_kind + '_away'])
            if side == 'Home':
                selected_odds = filtered[odds_kind + '_home']
            elif side == 'Away':
                selected_odds = filtered[odds_kind + '_away']
            else:
                selected_odds = filtered[[odds_kind + '_home', odds_kind + '_away']].min(axis=1)
            filtered = filtered[selected_odds.between(min_odds, max_odds)]
        if xg_filter != 'No xG filter':
            if xg_filter == 'Home xG at least':
                filtered = filtered[filtered.HT_xG_home >= min_xg]
            elif xg_filter == 'Away xG at least':
                filtered = filtered[filtered.HT_xG_away >= min_xg]
            else:
                trailing_home = filtered.HT_home < filtered.HT_away
                trailing_away = filtered.HT_away < filtered.HT_home
                filtered = filtered[(trailing_home & (filtered.HT_xG_home >= min_xg)) | (trailing_away & (filtered.HT_xG_away >= min_xg))]
        st.metric('Matching historical matches', len(filtered))
        if len(filtered):
            outcomes = {
                'Home win': int((filtered.FT_home > filtered.FT_away).sum()),
                'Draw': int((filtered.FT_home == filtered.FT_away).sum()),
                'Away win': int((filtered.FT_home < filtered.FT_away).sum()),
            }
            result_rows = [{'Outcome': label, 'Matches': count, 'Historical rate': f'{count / len(filtered):.1%}', 'Reciprocal odds': round(len(filtered) / count, 2) if count else None} for label, count in outcomes.items()]
            st.dataframe(pd.DataFrame(result_rows), hide_index=True, use_container_width=True)
            st.caption('Reciprocal odds are 1 / historical frequency, not model-validated fair odds. Small samples can be highly misleading.')
            st.dataframe(filtered[['date', 'home', 'away', 'HT_home', 'HT_away', 'FT_home', 'FT_away', 'HT_xG_home', 'HT_xG_away', 'opening_home', 'opening_away', 'last_seen_home', 'last_seen_away']], hide_index=True, use_container_width=True)
        else:
            st.info('No imported matches meet these filters. Try broader filters or import more matches.')
