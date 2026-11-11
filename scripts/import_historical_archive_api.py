"""Import a vetted archive through Supabase REST using server-side secrets.

Only writes the four archive_* staging tables. Never put secrets or archives in
a public repository. The ZIP is supplied at runtime, not committed to GitHub.
"""
import csv
import io
import json
import os
import sys
import time
import unicodedata
import re
import zipfile
from collections import defaultdict
from urllib import request, parse, error

BATCH = 150
TABLES = ("archive_football_data", "archive_understat",
          "archive_understat_goal_events", "archive_source_links")
FILES = ("football_data_pre2022.csv", "understat_pre2022.csv",
         "understat_verified_goal_events_pre2022.csv",
         "cross_source_links_pre2022.csv")

def rows(z, name):
    with z.open(name) as raw:
        yield from csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig"))

def yes(v):
    return str(v).lower() in ("1", "true")

def numeric(v):
    return None if v in ("", None) else float(v)

def key(v):
    s = unicodedata.normalize("NFKD", v).encode("ascii", "ignore").decode("ascii")
    return re.sub("[^a-z0-9]", "", s.lower())

def payload(r, numeric_prefixes, excluded=()):
    return {k: numeric(v) if k.startswith(numeric_prefixes) and k != "ht_xg_timing_convention" else v
            for k, v in r.items() if k not in excluded and v != ""}

def football(r):
    return dict(archive_key=r["archive_key"], match_date=r["date"],
        league=r["league"], home_team=r["home"], away_team=r["away"],
        has_ft_score=yes(r["has_ft_score"]), has_ht_score=yes(r["has_ht_score"]),
        has_corners=yes(r["has_corners"]), has_yellows=yes(r["has_yellows"]),
        has_b365_odds=yes(r["has_b365_odds"]), source_file=r["source_file"],
        source_row=int(r["source_row"]),
        payload=payload(r, ("ft_", "ht_", "corners_", "yellow_", "red_", "odds_"),
                        ("archive_key", "source_file", "source_row")))

def understat(r):
    return dict(understat_id=int(r["understat_id"]), match_date=r["date"],
        league=r["league"], home_team=r["home"], away_team=r["away"],
        verified_goal_sequence=yes(r["verified_goal_sequence"]),
        ht_xg_provisional=True,
        payload=payload(r, ("ft_", "ht_xg_", "full_xg_", "shot_xg_")))

def event(r):
    return dict(understat_id=int(r["understat_id"]),
        minute=int(float(r["minute"])), shot_team_side=r["shot_team_side"],
        result=r["result"], goal_attribution_verified=yes(r["goal_attribution_verified"]))

class API:
    def __init__(self):
        self.url = os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1/"
        self.secret = os.environ["SUPABASE_SECRET_KEY"]
        if not self.url.startswith("https://"):
            raise ValueError("SUPABASE_URL must be https")

    def call(self, table, method="GET", params=None, data=None, headers=None):
        url = self.url + table
        if params:
            url += "?" + parse.urlencode(params, safe="(),.*:")
        h = {"apikey": self.secret, "Content-Type": "application/json",
             "Accept": "application/json"}
        if headers: h.update(headers)
        body = None if data is None else json.dumps(data).encode()
        for attempt in range(6):
            req = request.Request(url, data=body, method=method, headers=h)
            try:
                with request.urlopen(req, timeout=60) as resp:
                    raw = resp.read()
                    return json.loads(raw) if raw else []
            except error.HTTPError as exc:
                detail = exc.read(600).decode(errors="replace")
                if exc.code not in (429, 500, 502, 503, 504) or attempt == 5:
                    raise RuntimeError(f"Supabase {table} HTTP {exc.code}: {detail}") from None
                time.sleep(min(2 ** attempt, 20))
        raise RuntimeError("Retry limit exceeded")

    def insert(self, table, records, conflict=None):
        batch = []
        count = 0
        for record in records:
            batch.append(record)
            if len(batch) >= BATCH:
                self._write(table, batch, conflict)
                count += len(batch)
                batch.clear()
        if batch:
            self._write(table, batch, conflict)
            count += len(batch)
        print(f"{table}: {count} input rows processed", flush=True)

    def _write(self, table, batch, conflict):
        params = {"on_conflict": conflict} if conflict else None
        preference = "return=minimal"
        if conflict: preference += ",resolution=ignore-duplicates"
        self.call(table, "POST", params, batch, {"Prefer": preference})

    def ids(self, table, column):
        found = set()
        start = 0
        while True:
            page = self.call(table, params={"select": column, "order": column + ".asc",
                "limit": 1000, "offset": start})
            found.update(int(r[column]) for r in page)
            if len(page) < 1000: return found
            start += len(page)

def main(archive):
    api = API()
    with zipfile.ZipFile(archive) as z:
        missing = set(FILES) - set(z.namelist())
        if missing: raise ValueError("Archive missing: " + ", ".join(sorted(missing)))
        with z.open("football_data_pre2022.csv") as raw:
            fd_index = {}
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig"))
            for r in reader:
                match = (r["date"], r["league"], r["source_file"],
                         key(r["home"]), key(r["away"]))
                fd_index.setdefault(match, []).append(r["archive_key"])
        api.insert("archive_football_data",
                   (football(r) for r in rows(z, FILES[0])), "archive_key")
        api.insert("archive_understat",
                   (understat(r) for r in rows(z, FILES[1])), "understat_id")

        # Event table has a generated identity, not a natural unique key.
        # Skip complete match groups on reruns; repair the known one-event seed.
        existing = api.ids("archive_understat_goal_events", "understat_id")
        grouped = defaultdict(list)
        for r in rows(z, FILES[2]):
            grouped[int(r["understat_id"])].append(event(r))
        if 5447 in existing and len(grouped.get(5447, [])) > 1:
            # Seed match 5447 was populated with only one trial goal event.
            api.call("archive_understat_goal_events", "DELETE",
                     {"understat_id": "eq.5447"})
            existing.remove(5447)
        to_add = (ev for match_id, group in grouped.items()
                  if match_id not in existing for ev in group)
        api.insert("archive_understat_goal_events", to_add)

        links = []
        unresolved = 0
        conflicts = 0
        for r in rows(z, FILES[3]):
            if not yes(r["score_agrees"]):
                conflicts += 1
                continue
            match = (r["date"], r["football_data_league"],
                     r["football_data_source"], key(r["home"]), key(r["away"]))
            keys = fd_index.get(match, [])
            if len(keys) != 1:
                unresolved += 1
                continue
            links.append(dict(understat_id=int(r["understat_id"]),
                              archive_key=keys[0], score_agrees=True))
        api.insert("archive_source_links", links, "understat_id")
        print(f"Unresolved links: {unresolved}; score conflicts: {conflicts}", flush=True)
        for table in TABLES:
            print(f"Validated API access: {table}",
                  len(api.call(table, params={"select": "*" ,"limit": 1})),
                  "sample row(s)", flush=True)
    print("ARCHIVE IMPORT FINISHED; existing non-archive tables untouched", flush=True)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/import_historical_archive_api.py archive.zip")
    main(sys.argv[1])
