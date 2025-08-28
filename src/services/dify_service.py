# services/dify_service.py

from __future__ import annotations
import os
import json
import time
import threading
from datetime import datetime
from typing import Dict, Optional, Callable, Any, List
import requests
import sseclient
import streamlit as st
from services.dedup import dedup_questions

try:
    from streamlit.runtime.scriptrunner import add_script_run_ctx
except ImportError:
    def add_script_run_ctx(thread): return thread

# ==============================
# Dify: 状態管理とヘルパー
# ==============================
def _to_str(x: Any) -> str:
    if x is None: return ""
    return str(x) if isinstance(x, (str, int, float)) else json.dumps(x, ensure_ascii=False)

def _cap(s: str, limit: int) -> str:
    return s if len(s) <= limit else s[:limit-3] + "..."

def _init_dify_debug_state():
    defaults = {
        "dify_last_payload": {}, "dify_last_response": {}, "dify_last_error": "", "dify_last_ran_at": "",
        "dify_busy": False, "dify_next_after": 0.0, "meeting_started": False,
        "dify_status_log": [],
        "dify_api_base": os.getenv("DIFY_API_BASE", "https://api.dify.ai"),
        "dify_api_key": os.getenv("DIFY_API_KEY", ""),
        "dify_endpoint_type": os.getenv("DIFY_ENDPOINT_TYPE", "workflow"),
        "dify_workflow_id": os.getenv("DIFY_WORKFLOW_ID", ""),
        "dify_streaming": os.getenv("DIFY_RESPONSE_MODE", "streaming").lower() == "streaming"
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)

def dify_busy() -> bool: return st.session_state.dify_busy
def dify_mark_busy(flag: bool): st.session_state.dify_busy = flag
def dify_mark_next_after(seconds: float): st.session_state.dify_next_after = time.monotonic() + seconds
def dify_next_ok() -> bool: return time.monotonic() >= st.session_state.dify_next_after

def _status(msg: str):
    log = st.session_state.dify_status_log
    log.append(f"{datetime.now().strftime('%H:%M:%S')}  {msg}")
    st.session_state.dify_status_log = log[-500:]

# ==============================
# Dify 入力収集
# ==============================
def collect_inputs_for_dify() -> Dict[str, str]:
    profile = st.session_state.get("profile", {})
    company_info = "\n".join(f"{k}: {v}" for k, v in profile.items() if v).strip()

    questions = st.session_state.get("questions", [])
    q_lines = []
    for q in questions:
        pr = int(float(q.get("priority", 50)))
        tags = ", ".join(q.get("tags", []))
        q_lines.append(f"[{q.get('status', '')}] p={pr} {q.get('text', '')} #{tags}".strip())
    q_list_old = "\n".join(q_lines)

    memo = st.session_state.get("note_text_snapshot", "")
    # memo = st.session_state.get("summary_markdown", "")
    # transcript_list = st.session_state.get("transcript", [])
    # transcript = "\n".join([f"{ts}: {text}" for ts, text in transcript_list[-200:]])
    transcript = st.session_state.get("summary_markdown", "")
    
    shodan_phase = st.session_state.get("shodan_phase", "現状・課題・ニーズ把握")

    return {
        "company_info": _to_str(company_info),
        "q_list_old": _to_str(q_list_old),
        "shodan_memo": _cap(_to_str(memo), 4000),
        "shodan_mojiokoshi": _to_str(transcript),
        "shodan_phase": _to_str(shodan_phase),
    }

# ==============================
# Dify API 呼び出し
# ==============================
def _resolve_api_base() -> str:
    return st.session_state.dify_api_base.rstrip("/")

def _mask(s: str) -> str:
    return s[:3] + "*" * (len(s) - 6) + s[-3:] if len(s) > 6 else "*" * len(s)

def call_dify(inputs: Dict, on_event: Optional[Callable] = None) -> Dict:
    rm = "streaming" if st.session_state.dify_streaming else "blocking"
    endpoint_type = st.session_state.dify_endpoint_type
    api_key = st.session_state.dify_api_key
    user_id = os.getenv("DIFY_USER_ID", "Sales-Agent")
    url = f"{_resolve_api_base()}/v1/{'workflows/run' if endpoint_type == 'workflow' else 'chat-messages'}"
    
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {"inputs": inputs, "response_mode": rm, "user": user_id}

    if endpoint_type == "workflow":
        body["workflow_id"] = st.session_state.dify_workflow_id
        if not body["workflow_id"]: raise ValueError("Workflow IDが未設定です")
    else:
        body["query"] = "質問リストを生成してください。"

    if rm == "blocking":
        r = requests.post(url, headers=headers, json=body, timeout=120)
        r.raise_for_status()
        return r.json()

    with requests.post(url, headers=headers, json=body, stream=True, timeout=300) as r:
        r.raise_for_status()
        client = sseclient.SSEClient(r)
        for event in client.events():
            try:
                data = json.loads(event.data)
                if data.get('event') == 'workflow_finished':
                    return data
            except json.JSONDecodeError:
                continue
    return {}

# ==============================
# 出力パース
# ==============================
# def _parse_dify_output(resp: dict) -> List[Dict]:
#     try:
#         data = resp.get("data", {})
#         outputs = data.get("outputs", {})
#         q_list_candidate = None

#         if isinstance(outputs.get("structured_output"), dict):
#             q_list_candidate = outputs["structured_output"].get("q_list")
#         if q_list_candidate is None:
#             q_list_candidate = outputs.get("q_list")

#         q_list = []
#         if isinstance(q_list_candidate, str):
#             try: q_list = json.loads(q_list_candidate)
#             except json.JSONDecodeError: q_list = []
#         elif isinstance(q_list_candidate, list):
#             q_list = q_list_candidate
        
#         if not isinstance(q_list, list): return []

#         out: List[Dict] = []
#         valid_status = {"unanswered", "on_hold", "take_home", "resolved"}
#         alias_map = {
#             "pending": "unanswered", "open": "unanswered", "onhold": "on_hold",
#             "hold": "on_hold", "takehome": "take_home", "answered": "resolved",
#             "done": "resolved", "completed": "resolved",
#         }

#         for it in q_list:
#             if not isinstance(it, dict):
#                 if isinstance(it, str) and it.strip():
#                     out.append({"id": None, "text": it.strip(), "priority": 50, "tags": [], "status": "unanswered"})
#                 continue

#             text = (it.get("q") or it.get("text") or "").strip()
#             if not text: continue
            
#             try: priority = float(it.get("score", 50.0))
#             except (ValueError, TypeError): priority = 50.0

#             tags = it.get("tag") or it.get("tags") or []
#             if isinstance(tags, str):
#                 tags = [tag.strip() for tag in tags.split(',') if tag.strip()]
#             elif not isinstance(tags, list): tags = []

#             raw_status = (it.get("status") or "unanswered").strip().lower()
#             status = alias_map.get(raw_status, raw_status)
#             if status not in valid_status: status = "unanswered"

#             out.append({"id": None, "text": text, "priority": priority, "tags": tags, "status": status})
            
#         st.session_state["debug_parsed_qs"] = out
#         return out

#     except Exception as e:
#         st.session_state["dify_last_error"] = f"パース処理中に予期せぬエラーが発生しました: {type(e).__name__}: {e}"
#         return []

def _parse_dify_output(resp: dict) -> List[Dict]:
    try:
        # ステップ1: 現在の質問リストを st.session_state から取得
        existing_questions = st.session_state.get("questions", [])

        # ステップ2: Difyのレスポンスから新しい質問をパース（既存のロジック）
        data = resp.get("data", {})
        outputs = data.get("outputs", {})
        q_list_candidate = None

        if isinstance(outputs.get("structured_output"), dict):
            q_list_candidate = outputs["structured_output"].get("q_list")
        if q_list_candidate is None:
            q_list_candidate = outputs.get("q_list")

        q_list = []
        if isinstance(q_list_candidate, str):
            try: q_list = json.loads(q_list_candidate)
            except json.JSONDecodeError: q_list = []
        elif isinstance(q_list_candidate, list):
            q_list = q_list_candidate
        
        if not isinstance(q_list, list): 
            return existing_questions # パース失敗時は既存リストをそのまま返す

        # 新しくパースした質問を格納するリスト
        newly_parsed_questions: List[Dict] = []
        valid_status = {"unanswered", "on_hold", "take_home", "resolved"}
        alias_map = {
            "pending": "unanswered", "open": "unanswered", "onhold": "on_hold",
            "hold": "on_hold", "takehome": "take_home", "answered": "resolved",
            "done": "resolved", "completed": "resolved",
        }

        for it in q_list:
            if not isinstance(it, dict):
                if isinstance(it, str) and it.strip():
                    newly_parsed_questions.append({"id": None, "text": it.strip(), "priority": 50, "tags": [], "status": "unanswered"})
                continue

            text = (it.get("q") or it.get("text") or "").strip()
            if not text: continue
            
            try: priority = float(it.get("score", 50.0))
            except (ValueError, TypeError): priority = 50.0

            tags = it.get("tag") or it.get("tags") or []
            if isinstance(tags, str):
                tags = [tag.strip() for tag in tags.split(',') if tag.strip()]
            elif not isinstance(tags, list): tags = []

            raw_status = (it.get("status") or "unanswered").strip().lower()
            status = alias_map.get(raw_status, raw_status)
            if status not in valid_status: status = "unanswered"

            newly_parsed_questions.append({"id": None, "text": text, "priority": priority, "tags": tags, "status": status})
        
        # デバッグ用に、今回新たに追加された質問のみを保存
        st.session_state["debug_parsed_qs"] = newly_parsed_questions
        
        if not newly_parsed_questions:
            return existing_questions # 新しい質問がなければ既存リストをそのまま返す

        # ステップ3: 既存リストと新しいリストをマージし、重複を排除
        merged_list = existing_questions + newly_parsed_questions
        final_list = dedup_questions(merged_list, threshold=0.9)

        # ステップ4: 完全な質問リストを返す
        return final_list

    except Exception as e:
        st.session_state["dify_last_error"] = f"パース処理中に予期せぬエラーが発生しました: {type(e).__name__}: {e}"
        # エラー発生時も既存のリストを返すことで、UI上のリストが消えるのを防ぐ
        return st.session_state.get("questions", [])

# ==============================
# 非同期実行
# ==============================
def run_dify_once_async(trigger: str):
    if dify_busy() or not dify_next_ok(): return

    def _job():
        dify_mark_busy(True)
        try:
            _status(f"実行トリガー: {trigger}")
            inputs = collect_inputs_for_dify()
            st.session_state.dify_last_payload = inputs
            
            resp = call_dify(inputs)
            st.session_state.dify_last_response = resp
            
            new_qs = _parse_dify_output(resp)

            if new_qs:
                st.session_state.questions = new_qs
                st.session_state.questions_source = "dify"
            
            st.rerun()

        except Exception as e:
            _status(f"エラー: {e}")
            st.session_state.dify_last_error = str(e)
        finally:
            dify_mark_busy(False)
            dify_mark_next_after(10.0)

    thread = threading.Thread(target=_job, daemon=True)
    add_script_run_ctx(thread)
    thread.start()
