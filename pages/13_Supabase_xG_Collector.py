"""Pro Star Lizard: cautious, resumable multi-league xG collection."""
from datetime import date
import math, os, time
import pandas as pd
import requests
import streamlit as st
from supabase import create_client

st.set_page_config(page_title='Star Lizard | Multi-League Collector', layout='centered')
st.title('Pro Star Lizard | Multi-League xG Collector')
st.caption('Verify competition listings first. New xG records are saved directly to Supabase.')
BASE='https://api.thestatsapi.com/api'
COLS=['Match ID','Date','Home','Away','Home xG','Away xG']
LEAGUES={'Premier League':'comp_3039','Championship':'comp_8321','Bundesliga':'comp_4643','Ligue 1':'comp_0256','Belgian Pro League':'comp_8531'}
key=st.secrets.get('STATS_API_KEY',os.environ.get('STATS_API_KEY',''))
if not key:
    st.error('Missing STATS_API_KEY in Streamlit secrets.');st.stop()

def clean(frame):
    if frame is None or frame.empty:return pd.DataFrame(columns=COLS)
    d=frame.copy()
    for c in COLS:
        if c not in d:d[c]=None
    d=d[COLS]
    d['Date']=pd.to_datetime(d['Date'],errors='coerce').dt.strftime('%Y-%m-%d')
    for c in ['Home xG','Away xG']:d[c]=pd.to_numeric(d[c],errors='coerce')
    for c in ['Home','Away']:d[c]=d[c].astype('string').str.strip()
    d=d.dropna(subset=['Date','Home','Away','Home xG','Away xG'])
    d=d[(d['Home xG']>=0)&(d['Away xG']>=0)&(d['Home']!='')&(d['Away']!='')]
    ids=d['Match ID'].astype('string')
    d['_key']=ids.where(ids.str.startswith('mt_',na=False),d['Date']+'|'+d['Home']+'|'+d['Away'])
    return d.drop_duplicates('_key',keep='last').drop(columns='_key').reset_index(drop=True)

# Supabase is the permanent source of truth; never rely on a local CSV for saved history.
try:
    db = create_client(st.secrets['SUPABASE_URL'], st.secrets['SUPABASE_SECRET_KEY'])
except Exception as exc:
    st.error(f'Cannot initialize Supabase: {exc}')
    st.stop()

DB_COLS = 'match_id,match_date,home_team,away_team,home_xg,away_xg'

def load_history():
    records = []
    offset = 0
    while True:
        response = (db.table('historical_xg').select(DB_COLS)
                    .range(offset, offset + 999).execute())
        chunk = response.data or []
        records.extend(chunk)
        if len(chunk) < 1000:
            break
        offset += 1000
    return clean(pd.DataFrame([{
        'Match ID': r['match_id'], 'Date': r['match_date'],
        'Home': r['home_team'], 'Away': r['away_team'],
        'Home xG': r['home_xg'], 'Away xG': r['away_xg']
    } for r in records]))

def save_new_rows(rows, existing):
    # Check BOTH provider match IDs and date/team identity, because older
    # imported rows have legacy_ IDs instead of TheStatsAPI mt_ IDs.
    known_ids = set(existing['Match ID'].dropna().astype(str))
    known_games = set(existing['Date'].astype(str) + '|' +
                      existing['Home'].astype(str).str.casefold() + '|' +
                      existing['Away'].astype(str).str.casefold())
    inserted = 0
    errors = []
    for r in rows:
        identity = f"{r['Date']}|{r['Home'].casefold()}|{r['Away'].casefold()}"
        if str(r['Match ID']) in known_ids or identity in known_games:
            continue
        payload = {
            'match_id': str(r['Match ID']), 'match_date': str(r['Date']),
            'home_team': str(r['Home']), 'away_team': str(r['Away']),
            'home_xg': float(r['Home xG']), 'away_xg': float(r['Away xG'])
        }
        try:
            db.table('historical_xg').insert(payload).execute()
            inserted += 1
            known_ids.add(payload['match_id'])
            known_games.add(identity)
        except Exception as exc:
            errors.append(f"{r['Match ID']}: {exc}")
    return inserted, errors

try:
    st.session_state.ml_rows = load_history()
except Exception as exc:
    st.error(f'Could not read Supabase history: {exc}')
    st.stop()

if 'ml_last' not in st.session_state:st.session_state.ml_last=0.0
if 'ml_found' not in st.session_state:st.session_state.ml_found=[]
if 'ml_verified' not in st.session_state:st.session_state.ml_verified=False
if 'ml_notice' not in st.session_state:st.session_state.ml_notice=''

session=requests.Session()
session.headers.update({'Authorization':f'Bearer {key}','Accept':'application/json'})
def api(path,params=None):
    for attempt in range(3):
        pause=1.8-(time.monotonic()-st.session_state.ml_last)
        if pause>0:time.sleep(pause)
        st.session_state.ml_last=time.monotonic()
        try:r=session.get(BASE+path,params=params,timeout=35)
        except requests.RequestException as exc:
            if attempt==2:return None,str(exc)
            time.sleep(5);continue
        if r.status_code==200:
            try:return r.json().get('data'),None
            except ValueError:return None,'Invalid JSON'
        if r.status_code==429 and attempt<2:
            try:retry=float(r.headers.get('Retry-After','0'))
            except ValueError:retry=0
            wait=min(120,max(retry,40))
            st.warning(f'Rate limit. Waiting {wait:.0f} seconds before retry.')
            time.sleep(wait);continue
        return None,f'HTTP {r.status_code}: {r.text[:200]}'
    return None,'API retries exhausted'

def get_name(v):return str(v.get('name','')) if isinstance(v,dict) else ''
def get_id(v):return str(v.get('id','')) if isinstance(v,dict) else ''
def read_xg(data,side):
    if not isinstance(data,dict):return None
    for section in data.values():
        if isinstance(section,dict) and 'expected_goals' in section:
            value=section['expected_goals']
            if isinstance(value,dict) and isinstance(value.get('all'),dict):
                try:
                    x=float(value['all'][side]);return x if math.isfinite(x) and x>=0 else None
                except (KeyError,TypeError,ValueError):pass
    return None

st.subheader('1. Existing history')
st.metric('Saved matches loaded',len(st.session_state.ml_rows))
st.caption('Loaded directly from Supabase. Existing records are not changed.')

st.subheader('2. Check a competition')
league=st.selectbox('League',list(LEAGUES))
comp=LEAGUES[league]
start=st.date_input('From',date(2025,8,1))
end=st.date_input('Through',date.today())
page=st.number_input('Fixture page',min_value=1,max_value=100,value=1,step=1)
limit=st.slider('Fixtures to inspect',5,50,20,5)
st.info('Competition filtering is not yet verified for this API. The first request is a safe probe: results are rejected unless each match explicitly identifies the selected competition.')
if st.button('Test league fixture listing',type='primary'):
    st.session_state.ml_verified=False
    st.session_state.ml_found=[]
    if start>end:st.error('Start date must precede end date.')
    else:
        params={'competition_id':comp,'status':'finished','date_from':str(start),'date_to':str(end),'per_page':limit,'page':int(page),'sort':'-utc_date'}
        data,err=api('/football/matches',params)
        if err:st.error(err)
        elif not isinstance(data,list):st.error('Unexpected response shape. No detailed requests sent.')
        elif not data:st.warning('No fixtures returned. The API may use a different competition filter or date field.')
        else:
            def league_id(m):
                for k in ['competition','league','tournament']:
                    v=m.get(k)
                    if isinstance(v,dict):return str(v.get('id',''))
                for k in ['competition_id','league_id','tournament_id']:
                    if m.get(k):return str(m[k])
                return ''
            tagged=[league_id(m) for m in data if isinstance(m,dict)]
            good=[m for m in data if isinstance(m,dict) and league_id(m)==comp and m.get('id')]
            st.session_state.ml_found=good
            st.session_state.ml_verified=(len(good)==len(data) and len(data)>0)
            st.session_state.ml_notice=f'{len(data)} fixtures returned; {len(good)} explicitly match {comp}. Competition tags: {sorted(set(tagged))}.'
            if st.session_state.ml_verified:st.success(st.session_state.ml_notice)
            else:st.error(st.session_state.ml_notice+' Detailed xG collection is blocked to prevent mixing leagues.')

if st.session_state.ml_notice:st.caption(st.session_state.ml_notice)
found=st.session_state.ml_found
if found:
    st.dataframe(pd.DataFrame([{'Date':str(m.get('utc_date',''))[:10],'Home':get_name(m.get('home_team')),'Away':get_name(m.get('away_team')),'Match ID':m.get('id')} for m in found]),hide_index=True,use_container_width=True)

st.subheader('3. Fetch missing xG only')
if st.session_state.ml_verified:
    known_ids=set(st.session_state.ml_rows['Match ID'].dropna().astype(str))
    known_fallback=set(st.session_state.ml_rows['Date'].astype(str)+'|'+st.session_state.ml_rows['Home'].astype(str)+'|'+st.session_state.ml_rows['Away'].astype(str))
    missing=[]
    for m in found:
        h,a=m.get('home_team'),m.get('away_team')
        d=str(m.get('utc_date',''))[:10]
        if not get_name(h) or not get_name(a) or not d:continue
        if str(m['id']) not in known_ids and d+'|'+get_name(h)+'|'+get_name(a) not in known_fallback:missing.append(m)
    st.write(f'{len(missing)} missing detailed xG records among {len(found)} verified fixtures.')
    batch=st.slider('Maximum detailed requests this batch',1,20,5)
    if st.button('Fetch next missing xG batch',disabled=not missing):
        rows=[];fail=[]
        progress=st.progress(0)
        for i,m in enumerate(missing[:batch]):
            data,err=api(f"/football/matches/{m['id']}/stats")
            hx,ax=read_xg(data,'home'),read_xg(data,'away')
            if err or hx is None or ax is None:fail.append(f"{m['id']}: {err or 'xG unavailable'}")
            else:rows.append({'Match ID':m['id'],'Date':str(m.get('utc_date',''))[:10], 'Home':get_name(m.get('home_team')),'Away':get_name(m.get('away_team')),'Home xG':hx,'Away xG':ax})
            progress.progress((i+1)/min(batch,len(missing)))
        inserted, save_errors = save_new_rows(rows, st.session_state.ml_rows)
        try:
            st.session_state.ml_rows = load_history()
        except Exception as exc:
            st.error(f'Saved records may exist, but refresh failed: {exc}')
        if inserted:
            st.success(f'Saved {inserted} NEW xG matches to Supabase. Database now has {len(st.session_state.ml_rows)} matches.')
        elif rows and not save_errors:
            st.info('All fetched matches were already present; no duplicates added.')
        if save_errors:
            st.error('Database save failed for some matches. Do not assume they were saved: ' + '; '.join(save_errors[:5]))
        if fail:
            st.warning('xG unavailable / API errors: ' + '; '.join(fail[:8]))
        st.info('To collect another batch, retest the fixture page. Supabase retains saved matches between sessions.')
else:st.caption('First verify the competition listing above. No detailed API calls are allowed before verification.')

st.subheader('4. Backup (optional)')
st.download_button('Download backup CSV',
                   st.session_state.ml_rows.to_csv(index=False).encode('utf-8-sig'),
                   file_name='starlizard_xg_history_master.csv',
                   mime='text/csv')
st.caption('Supabase is the permanent storage. The CSV is an optional backup only.')
