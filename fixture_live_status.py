"""Small, dependency-free helpers for live fixture display.

Status is read from TheStatsAPI payload; no match state is inferred from kickoff.
"""
LIVE_STATUSES={"live","in_progress","inplay","in_play","first_half","second_half","1h","2h","ht","half_time","halftime","extra_time","et","penalties","penalty_shootout"}
FINAL_STATUSES={"finished","completed","full_time","ft","aet","after_extra_time","postponed","cancelled","abandoned"}
def fixture_status(item):
    raw=str(item.get("status") or "unknown").strip()
    normalized=raw.lower().replace(" ","_").replace("-","_")
    if normalized in LIVE_STATUSES:return "Live"
    if normalized in FINAL_STATUSES:return "Finished / not active"
    return "Scheduled / unknown"

def live_fixture_rows(fixtures):
    """Return only explicitly live fixtures, preserving API scores and statuses."""
    return [item for item in fixtures if fixture_status(item)=="Live"]
