from __future__ import annotations
import sqlite3, json, time, uuid, os, threading
from typing import Optional, Dict, Any

_DB_PATH = os.getenv("JOB_SQLITE_PATH", "app_src/data/jobs.db")
_LOCK = threading.Lock()

def init_local_job_db(path: Optional[str]=None):
    global _DB_PATH
    if path: _DB_PATH = path
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    with sqlite3.connect(_DB_PATH) as con:
        con.execute("""
        create table if not exists jobs(
            id text primary key,
            conversation_id text not null,
            status text not null,  -- RUNNING / COMPLETED / FAILED
            trigger text,
            input_digest text,
            started_at real not null,
            finished_at real,
            error text,
            output_json text
        );
        """)
        con.execute("create index if not exists idx_jobs_conv_status on jobs(conversation_id, status);")
        con.commit()

def create_job(conversation_id: str, trigger: str, input_digest: str) -> str:
    jid = str(uuid.uuid4())
    with _LOCK, sqlite3.connect(_DB_PATH) as con:
        cur = con.execute("select count(*) from jobs where conversation_id=? and status='RUNNING'", (conversation_id,))
        if cur.fetchone()[0] > 0:
            raise RuntimeError("job already running")
        con.execute("""insert into jobs(id, conversation_id, status, trigger, input_digest, started_at)
                       values(?,?,?,?,?,?)""", (jid, conversation_id, "RUNNING", trigger, input_digest, time.time()))
        con.commit()
    return jid

def finish_job(job_id: str, status: str, output_json: Optional[dict]=None, error: Optional[str]=None):
    with _LOCK, sqlite3.connect(_DB_PATH) as con:
        con.execute("""update jobs set status=?, finished_at=?, error=?, output_json=? where id=?""",
                    (status, time.time(), error, json.dumps(output_json, ensure_ascii=False) if output_json is not None else None, job_id))
        con.commit()

def get_latest_status(conversation_id: str) -> Dict[str, Any]:
    with sqlite3.connect(_DB_PATH) as con:
        con.row_factory = sqlite3.Row
        cur = con.execute("""select id, status, started_at, finished_at, error from jobs
                             where conversation_id=? order by started_at desc limit 1""", (conversation_id,))
        row = cur.fetchone()
        return dict(row) if row else {}

def get_output(job_id: str) -> Optional[dict]:
    with sqlite3.connect(_DB_PATH) as con:
        con.row_factory = sqlite3.Row
        cur = con.execute("select output_json from jobs where id=?", (job_id,))
        row = cur.fetchone()
        if not row or row["output_json"] is None: return None
        try:
            import json
            return json.loads(row["output_json"])
        except Exception:
            return None

src/sales_agent_pkg/services/job_store.py

