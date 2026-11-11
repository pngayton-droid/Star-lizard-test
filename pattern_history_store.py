"""Private server-side pattern scan snapshots, immutable and deduplicated."""
import hashlib
import json
import requests
import pandas as pd
from archive_data_engine import _credentials, ArchiveDataError

SCAN_VERSION="pattern-v1"

def _request(method, path, **kwargs):
    url,key=_credentials()
    headers={"apikey":key,"Authorization":"Bearer "+key}
    headers.update(kwargs.pop("headers",{}))
    try:
        response=requests.request(method,url+"/rest/v1/"+path,headers=headers,timeout=45,**kwargs)
        response.raise_for_status()
        return response.json() if response.content else []
    except (requests.RequestException, ValueError) as exc:
        raise ArchiveDataError("Private pattern history request failed") from exc

def snapshot_key(matches, settings):
    # Changes to input IDs/dates/score/data values produce a new snapshot identity.
    fields=["understat_id","match_date","ft_home","ft_away","corners_home","corners_away",
            "yellows_home","yellows_away","b365_home","b365_away","league",
            "has_corners","has_yellows"]
    normalized=matches.reindex(columns=fields).copy()
    normalized=normalized.sort_values("understat_id")
    normalized=normalized.astype("string").fillna("<NULL>")
    digest=hashlib.sha256(normalized.to_csv(index=False).encode("utf-8")).hexdigest()
    identity=json.dumps({"version":SCAN_VERSION,"data":digest,"settings":settings},sort_keys=True)
    return hashlib.sha256(identity.encode("utf-8")).hexdigest(),digest

def save_snapshot(matches, results, settings):
    key,signature=snapshot_key(matches,settings)
    records=json.loads(results.to_json(orient="records"))
    body={"scan_key":key,"scan_version":SCAN_VERSION,"input_signature":signature,
          "scan_settings":settings,"match_count":int(len(matches)),
          "segment_count":int(len(results)),
          "flagged_count":int(results["screen_flag"].sum()) if not results.empty else 0,
          "results":records}
    _request("POST","pattern_scan_history",json=body,
             headers={"Prefer":"resolution=ignore-duplicates,return=minimal"})
    return key

def list_snapshots(limit=25):
    records=_request("GET","pattern_scan_history",params={
        "select":"id,scan_key,scan_version,input_signature,scan_settings,created_at,match_count,segment_count,flagged_count",
        "order":"created_at.desc","limit":min(int(limit),100)})
    return pd.DataFrame(records)

def load_snapshot(scan_key):
    rows=_request("GET","pattern_scan_history",params={
        "select":"results,scan_settings,created_at,match_count","scan_key":"eq."+scan_key,"limit":1})
    return rows[0] if rows else None
