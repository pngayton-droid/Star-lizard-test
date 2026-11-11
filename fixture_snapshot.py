"""Pure helpers for repeatable and auditable fixture research snapshots.

Export is a research artefact, not a calibrated prediction or market signal.
"""
import json
from datetime import date
from datetime import datetime, timezone

SCHEMA_VERSION=2

def build_snapshot(fixture_name,fixture_date,competition_id,baseline,dossier,goals,asian,
                   observed_quote=None):
    """Return a JSON-serialisable, provenance-labelled fixture analysis."""
    required=("home_xg","away_xg","home_n","away_n","home_last","away_last")
    missing=[name for name in required if name not in baseline]
    if missing:raise ValueError("Missing baseline fields: "+", ".join(missing))
    fixture_day=date.fromisoformat(str(fixture_date)[:10])
    latest_dates=[date.fromisoformat(str(baseline[key])[:10]) for key in ("home_last","away_last")]
    future_inputs=any(d>fixture_day for d in latest_dates)
    return {
        "schema_version":SCHEMA_VERSION,
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "source":"PRO STARLIZARD research dashboard",
        "fixture":{"name":str(fixture_name),"date":str(fixture_date),
                   "competition_id":str(competition_id)},
        "model":{"name":"independent_poisson","calibrated":False,
                 "opposition_adjusted":False,"point_in_time_valid":False,
                 "no_known_future_observations":not future_inputs},
        "inputs":{"home_xg":baseline["home_xg"],"away_xg":baseline["away_xg"],
                  "home_venue_sample":baseline["home_n"],"away_venue_sample":baseline["away_n"],
                  "home_latest":baseline["home_last"],"away_latest":baseline["away_last"]},
        "venue_dossier":dossier,
        "goals_pricing":goals,
        "asian_pricing":asian,
        "observed_quote":observed_quote,
        "limitations":["Uncalibrated venue-based research intensities",
                       "No automated verified bookmaker quote",
                       "No live match-state ingestion",
                       "Venue summary may contain observations after the selected fixture date",
                       "No historical point-in-time backtest"]+(["Historical inputs include matches after the fixture date"] if future_inputs else [])}

def snapshot_json(snapshot):
    return json.dumps(snapshot,indent=2,sort_keys=True,allow_nan=False)
