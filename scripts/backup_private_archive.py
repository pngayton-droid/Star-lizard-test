"""Export private Supabase archive tables and source ZIP into an encrypted backup.
Run only in GitHub Actions with configured secrets; never upload plaintext.
"""
import csv
import hashlib
import json
import os
import pathlib
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
import requests

URL=os.environ["SUPABASE_URL"].rstrip("/")
KEY=os.environ["SUPABASE_SECRET_KEY"]
PASSPHRASE=os.environ["BACKUP_PASSPHRASE"]
if len(PASSPHRASE)<16:
    raise RuntimeError("BACKUP_PASSPHRASE must be at least 16 characters")
HEADERS={"apikey":KEY,"Authorization":"Bearer "+KEY}
TABLES={
    "archive_football_data":"archive_key",
    "archive_understat":"understat_id",
    "archive_understat_goal_events":"event_id",
    "archive_source_links":"understat_id",
    "pattern_scan_history":"id",
}
def check(resp):
    resp.raise_for_status()
    return resp

with tempfile.TemporaryDirectory() as tmp:
    root=pathlib.Path(tmp)
    counts={}
    for table,key in TABLES.items():
        out=root/(table+".jsonl")
        last=None
        n=0
        with out.open("w",encoding="utf-8") as f:
            while True:
                params={"select":"*","order":key+".asc","limit":1000}
                if last is not None:
                    params[key]="gt."+str(last)
                batch=check(requests.get(URL+"/rest/v1/"+table,headers=HEADERS,params=params,timeout=90)).json()
                if not batch: break
                for row in batch:
                    f.write(json.dumps(row,ensure_ascii=False,separators=(",",":"))+"\n")
                n+=len(batch)
                new=batch[-1][key]
                if last is not None and str(new)<=str(last) and not isinstance(new,(int,float)):
                    raise RuntimeError("Pagination failed for "+table)
                last=new
                if len(batch)<1000: break
        counts[table]=n
        print(table,n)
    # Supabase Storage download, using service key. Keep object private.
    obj=check(requests.get(URL+"/storage/v1/object/authenticated/starlizard-private-import/starlizard_import_ready.zip",
                           headers=HEADERS,timeout=180,stream=True))
    source=root/"starlizard_import_ready.zip"
    with source.open("wb") as f:
        for chunk in obj.iter_content(1024*1024):
            if chunk: f.write(chunk)
    manifest={"created_utc":datetime.now(timezone.utc).isoformat(),"tables":counts,
              "storage_object":"starlizard-private-import/starlizard_import_ready.zip",
              "storage_bytes":source.stat().st_size,
              "storage_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),
              "note":"Logical archive data export only; not a full PostgreSQL schema/roles/functions dump."}
    (root/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    archive=root/"plaintext.zip"
    with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in root.iterdir():
            if path!=archive: z.write(path,path.name)
    output=pathlib.Path(os.environ.get("BACKUP_OUTPUT","/tmp/starlizard-backup.zip.enc"))
    output.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run(["openssl","enc","-aes-256-cbc","-pbkdf2","-iter","200000",
                    "-salt","-in",str(archive),"-out",str(output),
                    "-pass","env:BACKUP_PASSPHRASE"],check=True)
    print("Encrypted backup created:",output.name,output.stat().st_size,"bytes")
