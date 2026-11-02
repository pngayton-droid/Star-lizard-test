"""Pro Star Lizard: cautious, resumable multi-league xG collection."""
from pathlib import Path
from datetime import date
import io, math, os, time
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title='Star Lizard | Multi-League Collector', layout='centered')
st.title('Pro Star Lizard | Multi-League xG Collector')
st.caption('Test competition-level fixtures first; collect in small batches, retain existing data and download after every batch.')
BASE='https://api.thestatsapi.com/api'
FILE=Path(__file__).resolve().parent.parent/'data'/'starlizard_xg_history_master.csv'
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

if 'ml_rows' not in st.session_state:
    try:st.session_state.ml_rows=clean(pd.read_csv(FILE)) if FILE.exists() else clean(None)
    except Exception as exc:st.error(f'Cannot read master CSV: {exc}');st.stop()
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
upload=st.file_uploader('Optional: merge an updated master CSV',type='csv')
if upload is not None and st.button('Merge uploaded CSV'):
    try:
        before=len(st.session_state.ml_rows)
        st.session_state.ml_rows=clean(pd.concat([st.session_state.ml_rows,pd.read_csv(upload)],ignore_index=True))
        st.success(f'History: {before} → {len(st.session_state.ml_rows)} matches.')
    except Exception as exc:st.error(f'Upload could not be read: {exc}')

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
        st.session_state.ml_rows=clean(pd.concat([st.session_state.ml_rows,pd.DataFrame(rows)],ignore_index=True))
        st.success(f'Added {len(rows)} records. Master now has {len(st.session_state.ml_rows)} matches.')
        if fail:st.warning('Not saved: '+'; '.join(fail[:8]))
        st.info('Download the master CSV below now. To collect another batch, retest the fixture page so missing counts update.')
else:st.caption('First verify the competition listing above. No detailed API calls are allowed before verification.')

st.subheader('4. Save your updated master')
st.download_button('Download updated master CSV',st.session_state.ml_rows.to_csv(index=False).encode('utf-8-sig'),file_name='starlizard_xg_history_master.csv',mime='text/csv',type='primary')
st.warning('This page does not write to GitHub automatically. After each batch, replace the master CSV in your repository data folder. Streamlit session storage can reset.')
