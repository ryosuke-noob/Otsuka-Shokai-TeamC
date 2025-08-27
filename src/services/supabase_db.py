from __future__ import annotations
from typing import Any, Dict, List, Optional
from . import api

# UI <-> DB ステータス変換
_UI_TO_DB = {"unanswered":"unanswered","on_hold":"on_hold","take_home":"take_home","resolved":"answered"}
_DB_TO_UI = {"unanswered":"unanswered","on_hold":"on_hold","take_home":"take_home","answered":"resolved","resolved":"resolved"}

def init_db(_db_path=None) -> None: return None

def seed_if_empty(_db_path=None, _scenario_dir=None) -> None:
    try:
        if not api.select("customers", {"select":"id","limit":"1"}):
            api.insert("customers", {"name":"デモ株式会社"})
        if not api.select("conversations", {"select":"id","limit":"1"}):
            api.insert("conversations", {"title":"初回商談（デモ）","customer_company":"デモ株式会社"})
    except Exception:
        pass

# --- customers ---
def list_customers(_db_path=None) -> List[Dict[str, Any]]:
    return api.select("customers", {"select":"id,name,updated_at,created_at","order":"updated_at.desc"})

def get_customer(_db_path, customer_id: str) -> Dict[str, Any]:
    rows = api.select("customers", {"select":"id,name,notes","id":f"eq.{customer_id}","limit":"1"})
    row = rows[0] if rows else {}
    extra={}
    try:
        import json
        if row.get("notes"): extra = json.loads(row["notes"])
    except Exception: extra={}
    return {
        "id":row.get("id"), "name":row.get("name",""),
        "industry": extra.get("industry",""), "size": extra.get("size",""),
        "usecase": extra.get("usecase",""), "kpi": extra.get("kpi",""),
        "budget_upper": extra.get("budget_upper",""), "deadline": extra.get("deadline",""),
        "constraints": extra.get("constraints",""),
    }

def upsert_customer(_db_path, payload: Dict[str, Any]) -> str:
    import json
    cid = payload.get("id")
    body = {
        "name": payload.get("name",""),
        "notes": json.dumps({
            "industry": payload.get("industry",""),
            "size": payload.get("size",""),
            "usecase": payload.get("usecase",""),
            "kpi": payload.get("kpi",""),
            "budget_upper": payload.get("budget_upper",""),
            "deadline": payload.get("deadline",""),
            "constraints": payload.get("constraints",""),
        }, ensure_ascii=False)
    }
    if cid:
        rows = api.patch("customers", {"id":f"eq.{cid}"}, body)
        return rows[0]["id"] if rows else cid
    rows = api.insert("customers", body); return rows[0]["id"] if rows else ""

# --- meetings ---
def _customer_name(customer_id: Optional[str]) -> Optional[str]:
    if not customer_id: return None
    row = get_customer(None, customer_id); return row.get("name")

def list_meetings(_db_path, customer_id: Optional[str]) -> List[Dict[str, Any]]:
    cname = _customer_name(customer_id)
    params = {"select":"id,title,started_at,updated_at,customer_company","order":"updated_at.desc"}
    if cname: params["customer_company"] = f"eq.{cname}"
    rows = api.select("conversations", params)
    out=[]
    for r in rows:
        dt = r.get("started_at") or r.get("updated_at")
        ds = (dt or "")[:10] if isinstance(dt,str) else ""
        out.append({"id":r["id"],"title":r.get("title","商談"),"meeting_date":ds})
    return out

def new_meeting(_db_path, customer_id: Optional[str], title: str) -> str:
    cname = _customer_name(customer_id) or ""
    rows = api.insert("conversations", {"title":title, "customer_company": cname})
    return rows[0]["id"] if rows else ""

# --- bundle / transcripts / notes ---
def _p_from_db(p):  # 0~1 or 0~100を0~1へ
    try:
        f=float(p); return f/100.0 if f>1.0 else f
    except: return 0.0

def get_meeting_bundle(_db_path, meeting_id: Optional[str]) -> Dict[str, Any]:
    if not meeting_id: return {"transcript": [], "questions": [], "notes": []}

    logs = api.select("transcripts", {"select":"id,transcript_text,created_at",
                                      "conversation_id": f"eq.{meeting_id}",
                                      "order":"created_at.asc","limit":"800"})
    transcript=[]
    for r in logs:
        ts=r.get("created_at",""); hhmmss = ts[11:19] if isinstance(ts,str) and len(ts)>=19 else ""
        transcript.append((hhmmss, r.get("transcript_text","")))

    qs = api.select("questions", {
        "select":"id,question_text,status,priority,created_at,updated_at,question_tags(tags:tags(id,name))",
        "conversation_id": f"eq.{meeting_id}","order":"created_at.asc"
    })
    def _tags(row):
        out=[]
        for it in (row.get("question_tags") or []):
            if isinstance(it, dict):
                if "name" in it: out.append(it["name"])
                elif "tags" in it and isinstance(it["tags"], dict) and "name" in it["tags"]:
                    out.append(it["tags"]["name"])
        u=[]; [u.append(x) for x in out if x not in u]; return u

    questions=[{
        "id": q["id"],
        "text": q.get("question_text",""),
        "tags": _tags(q),
        "role": "—",
        "priority": _p_from_db(q.get("priority",0)),
        "status": _DB_TO_UI.get(q.get("status","unanswered"),"unanswered"),
    } for q in qs]

    notes = api.select("notes", {"select":"id,content,created_at",
                                 "conversation_id": f"eq.{meeting_id}",
                                 "order":"created_at.asc"})
    return {"transcript": transcript, "questions": questions, "notes": notes}

def add_transcript_line(_db_path, meeting_id: str, ts_hhmmss: str, role: str, text: str) -> None:
    prefix = f"[{role}] " if role else ""
    api.insert("transcripts", {"conversation_id": meeting_id, "transcript_text": f"{prefix}{text}"})

def add_note(_db_path, meeting_id: str, content: str) -> None:
    """メモは 1:1（会話あたり1件）。存在すれば上書き、なければ作成。"""
    rows = api.select("notes", {"select":"id","conversation_id": f"eq.{meeting_id}","order":"created_at.asc","limit":"1"})
    if rows:
        api.patch("notes", {"id": f"eq.{rows[0]['id']}"}, {"content": content})
    else:
        api.insert("notes", {"conversation_id": meeting_id, "content": content})

# --- questions / tags ---
def _p_to_db(p):
    try:
        f=float(p); return int(round(f*100)) if f<=1.0 else int(round(f))
    except: return None

def upsert_questions(_db_path, meeting_id: str, questions: List[Dict[str, Any]]) -> None:
    for q in questions:
        qid = q.get("id")
        body = {
            "conversation_id": meeting_id,
            "question_text": q.get("text",""),
            "status": _UI_TO_DB.get(q.get("status","unanswered"), "unanswered")
        }
        pr=_p_to_db(q.get("priority"))
        if pr is not None: body["priority"]=pr

        if qid:
            api.patch("questions", {"id": f"eq.{qid}"}, body)
        else:
            created = api.insert("questions", body)
            if created: q["id"] = created[0]["id"]

        tags = q.get("tags") or []
        if tags and q.get("id"):
            _ensure_tags_and_link(q["id"], tags)

def _ensure_tags_and_link(question_id: str, tag_names: List[str]) -> None:
    all_tags = api.select("tags", {"select":"id,name","order":"created_at.asc"})
    name2id = {t["name"]: t["id"] for t in all_tags}
    missing = [n for n in tag_names if n not in name2id]
    for n in missing:
        try:
            rows = api.insert("tags", {"name": n})
            if rows: name2id[n]=rows[0]["id"]
        except Exception: pass
    links = [{"question_id": question_id, "tag_id": name2id[n]} for n in tag_names if n in name2id]
    if links:
        try: api.bulk_insert("question_tags", links, prefer_minimal=True)
        except Exception: pass
