from __future__ import annotations
import os, json, requests
from typing import Dict, Any, List
from dotenv import load_dotenv
from app_src.services import supabase_db as db
from app_src.services import job_store

load_dotenv()

DIFY_API_KEY = os.getenv("DIFY_API_KEY")
DIFY_WORKFLOW_ID = os.getenv("DIFY_WORKFLOW_ID")
DIFY_USER_ID = os.getenv("DIFY_USER_ID", "Sales-Agent")

def _collect_inputs(conversation_id: str) -> Dict[str, str]:
    """全てstringで。文字数も絞る（q_list_old<=48）"""
    bundle = db.get_meeting_bundle(None, conversation_id)

    # メモ（上書き1件想定）
    memo = ""
    if bundle.get("notes"):
        memo = (bundle["notes"][-1].get("content","") or "")

    # 書き起こし（直近50件）
    trans = "\n".join([t for _, t in bundle.get("transcript", [])][-50:])

    # 既存質問（先頭5件を短縮）
    qs = bundle.get("questions", [])[:5]
    compact = "; ".join([f"{(q.get('text','') or '')[:32]}[{int(round((q.get('priority') or 0)*100))}]" for q in qs])[:48]

    # 会社情報：customers.notes→name を簡易採用
    company_info = (db.get_customer(None, conversation_id).get("name","") or "")
    # 会話からは取れないケースがあるので空でもOK（Difyの入力仕様はstring必須）

    return {
        "company_info": str(company_info),
        "q_list_old": str(compact),
        "shodan_memo": str(memo),
        "shodan_mojiokoshi": str(trans),
    }

def _call_dify(inputs: Dict[str, str]) -> Dict[str, Any]:
    if not DIFY_API_KEY or not DIFY_WORKFLOW_ID:
        raise RuntimeError("DIFY_API_KEY / DIFY_WORKFLOW_ID が未設定です (.env)")
    url = "https://api.dify.ai/v1/workflows/run"
    headers = {"Authorization": f"Bearer {DIFY_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "workflow_id": DIFY_WORKFLOW_ID,
        "inputs": inputs,
        "response_mode": "blocking",
        "user": DIFY_USER_ID
    }
    r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=120)
    if r.status_code >= 400:
        raise RuntimeError(f"Dify Error {r.status_code}: {r.text}")
    return r.json()

def _parse_questions(resp: Dict[str, Any]) -> List[Dict[str, Any]]:
    """期待: {"questions":[{"text":"...","priority":0.7,"tags":["要件"]}, ...]} を緩く解釈"""
    obj = resp.get("data") if isinstance(resp, dict) and "data" in resp else resp
    cand = None
    for k in ("questions","output","result"):
        v = obj.get(k) if isinstance(obj, dict) else None
        if isinstance(v, list): cand=v; break
        if isinstance(v, dict) and isinstance(v.get("questions"), list): cand=v["questions"]; break
    if not isinstance(cand, list): return []
    out=[]
    for it in cand:
        if not isinstance(it, dict): continue
        txt = str(it.get("text","")).strip()
        if not txt: continue
        pr = it.get("priority", 0.5)
        try:
            pr = float(pr); pr = pr/100.0 if pr>1.0 else pr
        except: pr = 0.5
        tags = it.get("tags") or []
        if not isinstance(tags, list): tags=[str(tags)]
        out.append({"id": None, "text": txt, "priority": pr, "tags": tags, "status":"unanswered", "role":"—"})
    return out

def execute_job(job_id: str, conversation_id: str):
    inputs = _collect_inputs(conversation_id)
    try:
        resp = _call_dify(inputs)
        qs = _parse_questions(resp)
        out = {"inputs": inputs, "questions": qs, "raw": resp}
        job_store.finish_job(job_id, "COMPLETED", output_json=out, error=None)
    except Exception as e:
        job_store.finish_job(job_id, "FAILED", output_json={"inputs": inputs}, error=f"{type(e).__name__}: {e}")
