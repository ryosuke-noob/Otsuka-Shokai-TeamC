# app.py
from __future__ import annotations
import os
import re
import json
import time
import threading
from datetime import datetime
from typing import List, Dict, Optional, Callable

import pandas as pd
import requests
import sseclient
import streamlit as st
from dotenv import load_dotenv

from app_src.services import supabase_db as dbsvc
from app_src.services.priority import recompute_priorities
from app_src.services.dedup import dedup_questions

# --- add this safely ---
try:
    from streamlit.runtime.scriptrunner import add_script_run_ctx
except Exception:
    # 古いバージョンでも落ちないフォールバック
    def add_script_run_ctx(_t):
        return

# ==============================
# 基本設定
# ==============================
load_dotenv()
st.set_page_config(page_title="Sales Live Assist v3.3 (Local-first + Dify)", layout="wide")

if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_ANON_KEY"):
    st.error("環境変数 SUPABASE_URL / SUPABASE_ANON_KEY (.env) が未設定です。")
    st.stop()

dbsvc.init_db(None)
dbsvc.seed_if_empty(None, None)

# ==============================
# スタイル（暗転・モーダル禁止 / 余白 / 小物）
# ==============================
st.markdown(
    """
<style>
:root { --top-safe-area: 52px; }
.block-container { padding-top: calc(var(--top-safe-area) + .2rem) !important; }

/* ==== ダークオーバーレイを全面的に無効化 ==== */
[data-testid="stModal"],
[data-testid="stDialogOverlay"],
div[role="dialog"],
div[role="alertdialog"],
div[aria-modal="true"] {
  background: transparent !important;
  backdrop-filter: none !important;
}
[data-testid="stModal"] > div, div[role="dialog"] > div { box-shadow: none !important; }
.stSpinner, .stStatus { background: transparent !important; }

/* ==== バッジ / タグ ==== */
.badge { display:inline-block; padding:2px 6px; font-size:.8rem;
  border-radius:999px; border:1px solid rgba(255,255,255,.12); margin-right:.35rem; opacity:.85; }

/* ==== Top3 カード ==== */
.top3 .card { border:1px solid rgba(255,255,255,.09); background:rgba(255,255,255,.03);
  border-radius:16px; padding:12px; height:100%; }
.top3 h4 { margin:.2rem 0 .4rem 0; font-weight:800; }
.top3 .qtext { font-size:1.05rem; line-height:1.55rem; margin:.25rem 0 .5rem 0; }
.top3 .btnrow { display:grid; grid-template-columns:repeat(3,1fr); gap:.5rem; }
.top3 div[data-testid="stButton"] > button {
  border-radius:999px !important; border:1px solid rgba(255,255,255,.12); background:rgba(255,255,255,.04);
  height:44px; white-space:nowrap; padding:.4rem .6rem !important;
}

/* ==== 質問リスト 1行コンパクト ==== */
.row-compact { padding:.55rem .6rem; border:1px solid rgba(255,255,255,.08); border-radius:12px; }
.row-compact small { opacity:.8; }

/* ==== 小さなインライン情報帯 ==== */
.inline-info { padding:.3rem .6rem; border:1px solid rgba(255,255,255,.12); border-radius:8px; opacity:.9; }
</style>
""",
    unsafe_allow_html=True,
)

# ==============================
# 日本語/英語ステータス
# ==============================
JP = {"unanswered": "未取得", "on_hold": "保留中", "take_home": "持ち帰り", "resolved": "聞けた"}
JP_ORDER = ["未取得", "保留中", "持ち帰り", "聞けた"]
EN = {v: k for k, v in JP.items()}

# ==============================
# インライン状態表示（暗転なし）
# ==============================
from contextlib import contextmanager

@contextmanager
def inline_status(label: str = "処理中…"):
    holder = st.empty()
    holder.markdown(f"🛰️ {label}")
    try:
        yield
    finally:
        holder.empty()

# ==============================
# Dify: 文字列化 / 状態
# ==============================
def _to_str(x) -> str:
    if x is None: return ""
    if isinstance(x, str): return x
    try:
        return json.dumps(x, ensure_ascii=False)
    except Exception:
        return str(x)

def _cap(s: str, limit: int) -> str:
    s = s or ""
    return s if len(s) <= limit else s[: limit - 3] + "..."

def _init_dify_debug_state():
    ss = st.session_state
    # 送受信
    ss.setdefault("dify_last_payload", {})
    ss.setdefault("dify_last_response", {})
    ss.setdefault("dify_last_error", "")
    ss.setdefault("dify_last_ran_at", "")  # 表示用
    # 実行制御
    ss.setdefault("dify_busy", False)
    ss.setdefault("dify_next_after", 0.0)  # time.monotonic() 秒
    ss.setdefault("meeting_started", False)
    # streaming途中情報
    ss.setdefault("dify_partial_outputs", [])
    ss.setdefault("dify_partial_answer", "")
    ss.setdefault("dify_status_log", [])
    # 設定（サイドバーから上書き可能、未入力は .env を利用）
    ss.setdefault("dify_api_base", os.getenv("DIFY_API_BASE", "https://api.dify.ai"))
    ss.setdefault("dify_api_key", os.getenv("DIFY_API_KEY", ""))
    ss.setdefault("dify_endpoint_type", os.getenv("DIFY_ENDPOINT_TYPE", "workflow"))
    ss.setdefault("dify_workflow_id", os.getenv("DIFY_WORKFLOW_ID", ""))
    # 既定は streaming（UIで切替）
    ss.setdefault("dify_streaming", os.getenv("DIFY_RESPONSE_MODE", "streaming").lower() == "streaming")

_init_dify_debug_state()

def dify_busy() -> bool:
    return bool(st.session_state.get("dify_busy", False))

def dify_mark_busy(flag: bool):
    st.session_state["dify_busy"] = flag

def dify_mark_next_after(seconds: float):
    st.session_state["dify_next_after"] = time.monotonic() + seconds

def dify_next_ok() -> bool:
    return time.monotonic() >= float(st.session_state.get("dify_next_after", 0.0))

def now_hm():
    return datetime.now().strftime("%H:%M:%S")

def _status(msg: str):
    # バックグラウンドからUIを汚さずにログだけ蓄積
    st.session_state["dify_status_log"].append(f"{now_hm()}  {msg}")
    # ログは際限なく増えないように
    if len(st.session_state["dify_status_log"]) > 500:
        st.session_state["dify_status_log"] = st.session_state["dify_status_log"][-500:]

# ==============================
# サイドバー（設定タブ）
# ==============================
with st.sidebar:
    st.header("⚙️ 設定（Dify）")
    st.caption("ここでAPI情報とモードを切替できます。未入力は .env の値が使われます。")

    st.session_state.dify_api_base = st.text_input(
        "API Base", value=st.session_state.get("dify_api_base","https://api.dify.ai"),
        help="例: https://api.dify.ai"
    )

    st.session_state.dify_api_key = st.text_input(
        "API Key", value=st.session_state.get("dify_api_key",""), type="password"
    )

    st.session_state.dify_endpoint_type = st.selectbox(
        "エンドポイント種別", ["workflow", "chat"],
        index=0 if st.session_state.get("dify_endpoint_type","workflow") == "workflow" else 1
    )

    st.session_state.dify_workflow_id = st.text_input(
        "Workflow ID（workflow時）", value=st.session_state.get("dify_workflow_id","")
    )

    st.session_state.dify_streaming = st.toggle(
        "Streamingで実行（OFFならBlocking）",
        value=bool(st.session_state.get("dify_streaming", True))
    )

    st.divider()
    st.caption("💡 環境変数: DIFY_API_BASE / DIFY_API_KEY / DIFY_WORKFLOW_ID / DIFY_ENDPOINT_TYPE / DIFY_RESPONSE_MODE")

# ==============================
# Dify 入力収集
# ==============================
def collect_inputs_for_dify() -> dict:
    prof = st.session_state.get("profile", {}) or {}
    company_info = "\n".join(
        [
            f"会社名: {prof.get('name','')}",
            f"業種: {prof.get('industry','')}",
            f"規模: {prof.get('size','')}",
            f"用途: {prof.get('usecase','')}",
            f"KPI: {prof.get('kpi','')}",
            f"上限額: {prof.get('budget_upper','')}",
            f"導入希望: {prof.get('deadline','')}",
            f"制約: {prof.get('constraints','')}",
        ]
    ).strip()

    qs = st.session_state.get("questions", []) or []
    lines = []
    for q in qs:
        pr = q.get("priority", 0)
        pr100 = int(round(float(pr) * 100)) if float(pr) <= 1.0 else int(pr)
        status = q.get("status", "unanswered")
        tag_str = ", ".join(q.get("tags") or [])
        text = (q.get("text", "") or "").replace("\n", " ")
        lines.append(f"[{status}] p={pr100} {text}" + (f" #{tag_str}" if tag_str else ""))
    q_list_old = "\n".join(lines)

    memo_text = st.session_state.get("note_text", "") or ""
    shodan_memo = _cap(memo_text, 4000)

    trans = st.session_state.get("transcript", []) or []
    tail = trans[-200:] if len(trans) > 200 else trans
    shodan_mojiokoshi = "\n".join([f"{t}: {u}" for t, u in tail])

    return {
        "company_info": _to_str(company_info),
        "q_list_old": _to_str(q_list_old),
        "shodan_memo": _to_str(shodan_memo),
        "shodan_mojiokoshi": _to_str(shodan_mojiokoshi),
    }

# ==============================
# Dify呼び出し（blocking/streaming 両対応）
# ==============================
def _resolve_api_base() -> str:
    base = st.session_state.get("dify_api_base") or os.getenv("DIFY_API_BASE", "https://api.dify.ai")
    return base.rstrip("/")

def _mask(s: str) -> str:
    if not s: return ""
    if len(s) <= 6: return "*" * len(s)
    return s[:3] + "*" * (len(s)-6) + s[-3:]

def _stream_event_logger(etype: str, evt: Dict):
    data = evt.get("data") or {}
    node = (data or {}).get("node_title") or (data or {}).get("task_name") or etype
    if etype in ("workflow_started", "message_start"):
        _status(f"開始: {node}")
    elif etype == "node_started":
        _status(f"ノード開始: {node}")
    elif etype == "node_finished":
        _status(f"ノード完了: {node}")
    elif etype == "message_delta":
        # 断片受信（長文化防止のため記録は控えめ）
        chunk = (data or {}).get("answer") or ""
        if chunk:
            _status(f"受信: delta {len(chunk)}ch")
    elif etype in ("message_end", "workflow_finished"):
        _status("完了")
    else:
        _status(f"{etype}")

def call_dify(
    inputs: Dict,
    response_mode: Optional[str] = None,
    on_event: Optional[Callable[[str, Dict], None]] = None,
) -> Dict:
    """
    Dify API を blocking/streaming で呼び分ける（workflow / chat 両対応）。
    戻り値は {"data": {...}} に統一（最終イベント data）。
    """
    api_base = _resolve_api_base()
    endpoint_type = (st.session_state.get("dify_endpoint_type") or "workflow").lower()
    url = f"{api_base}/v1/workflows/run" if endpoint_type == "workflow" else f"{api_base}/v1/chat-messages"

    api_key = (st.session_state.get("dify_api_key") or os.getenv("DIFY_API_KEY","")).strip()
    wf_id = (st.session_state.get("dify_workflow_id") or os.getenv("DIFY_WORKFLOW_ID","")).strip()
    user_id = os.getenv("DIFY_USER_ID", "Sales-Agent").strip()

    if not api_key:
        raise RuntimeError("DIFY_API_KEY が未設定です (.env またはサイドバー)")
    if endpoint_type == "workflow" and not wf_id:
        raise RuntimeError("DIFY_WORKFLOW_ID が未設定です (.env またはサイドバー)")

    rm = (response_mode or ("streaming" if st.session_state.get("dify_streaming", True) else "blocking")).strip().lower()
    if rm not in ("streaming", "blocking"):
        rm = "blocking"

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if endpoint_type == "workflow":
        body = {"workflow_id": wf_id, "inputs": inputs, "response_mode": rm, "user": user_id}
    else:
        # chat: queryは固定文。ワークフローが基本なので簡易対応
        body = {"inputs": inputs, "query": "質問リストを生成してください。", "response_mode": rm, "user": user_id}

    # blocking
    if rm == "blocking":
        r = requests.post(url, headers=headers, json=body, timeout=120)
        r.raise_for_status()
        return r.json()

    # streaming (SSE)
    final_data = None
    with requests.post(url, headers=headers, json=body, stream=True, timeout=300) as r:
        r.raise_for_status()

        client = sseclient.SSEClient(r)
        for event in client.events():
            try:
                event_json = json.loads(event.data)
            except Exception:
                continue
            if event_json.get('event') == 'workflow_finished':
                outputs = (event_json.get("data") or {}).get("outputs") or {}
                so = outputs.get("structured_output") or {}
                q_list = so.get("q_list") or []
                final_data = {"outputs": {"q_list": q_list}}
                break

    return {"data": final_data or {}}

def _on_stream_event_side_effects(event_type: str, evt: Dict):
    """バックグラウンドスレッド側で session_state のみ更新（UIは触らない）"""
    data = evt.get("data") or {}

    # Chatの断片を連結
    ans_delta = (data or {}).get("answer") if isinstance(data, dict) else None
    if isinstance(ans_delta, str) and ans_delta:
        st.session_state["dify_partial_answer"] = st.session_state.get("dify_partial_answer", "") + ans_delta

    # ノード完了 outputs に questions_json があれば一時保存
    if event_type == "node_finished":
        outputs = (data or {}).get("outputs") or {}
        if isinstance(outputs, dict):
            try:
                raw = outputs.get("questions_json", "[]")
                arr = json.loads(raw) if isinstance(raw, str) else (raw or [])
                partial = [{
                    "text": (it.get("text","") or "").strip(),
                    "priority": (float(it.get("priority", 0)) / 100.0 if float(it.get("priority",0)) > 1 else float(it.get("priority",0))),
                    "tags": it.get("tags") or [],
                    "status": "unanswered"
                } for it in arr]
                st.session_state["dify_partial_outputs"] = partial
            except Exception:
                pass

# 既存API互換（必要なら継続利用）
def _call_dify_blocking(inputs: dict) -> dict:
    return call_dify(inputs, response_mode="blocking")

# ========= 出力パース =========
def _parse_bullet_questions(answer: str) -> List[Dict]:
    """chatの自由文から箇条書きを拾って簡易抽出"""
    out: List[Dict] = []
    for ln in answer.splitlines():
        if re.match(r"^\s*([-*・]|\d+\.)\s+", ln):
            txt = re.sub(r"^\s*([-*・]|\d+\.)\s+", "", ln).strip()
            if txt:
                out.append({"text": txt, "priority": 0.5, "tags": [], "status": "unanswered"})
    return out

# def _parse_dify_output(resp: dict) -> List[Dict]:
#     """
#     Difyのレスポンスから質問リストを抽出。
#     優先: data.outputs.q_list
#       - q        -> text
#       - score    -> priority（正規化なし）
#       - tag/tags -> tags (list[str])
#       - status   -> status（英語のまま）
#     """
#     try:
#         outputs = (resp or {}).get("data", {}).get("outputs", {}) or {}
#         q_list = outputs.get("q_list", [])
#         out: List[Dict] = []

#         # 許容ステータス（英語）
#         valid_status = {"unanswered", "on_hold", "take_home", "resolved"}

#         for it in q_list:
#             # 文字列のみのフォールバック
#             if not isinstance(it, dict):
#                 if isinstance(it, str) and it.strip():
#                     out.append({
#                         "text": it.strip(),
#                         "priority": 50,
#                         "tags": [],
#                         "status": "unanswered",
#                     })
#                 continue

#             text = (it.get("q") or it.get("text") or "").strip()
#             if not text:
#                 continue

#             # priority は score をそのまま利用（数値でなければ 50 にフォールバック）
#             score = it.get("score", 50)
#             try:
#                 priority = float(score)
#             except Exception:
#                 priority = 50

#             # tags は tag/tags どちらでも受け付ける
#             tags = it.get("tag") or it.get("tags") or []
#             if isinstance(tags, str):
#                 tags = [tags]
#             elif not isinstance(tags, list):
#                 tags = []

#             # status は英語のまま採用。未知値は安全に 'unanswered' へ。
#             raw_status = (it.get("status") or "").strip().lower()
#             # ゆるい同義語の吸収（万一API側で表記ブレがあった場合の保険）
#             alias_map = {
#                 "pending": "unanswered",
#                 "open": "unanswered",
#                 "onhold": "on_hold",
#                 "hold": "on_hold",
#                 "takehome": "take_home",
#                 "answered": "resolved",
#                 "done": "resolved",
#                 "completed": "resolved",
#             }
#             status = alias_map.get(raw_status, raw_status)
#             if status not in valid_status:
#                 status = "unanswered"

#             out.append({
#                 "text": text,
#                 "priority": priority,
#                 "tags": tags,
#                 "status": status,
#             })

#         # デバッグ用メモ
#         st.session_state["debug_parse_path"] = "data.outputs.q_list"
#         st.session_state["debug_parsed_count"] = len(out)

#         return out

#     except Exception as e:
#         st.session_state["dify_last_error"] = f"_parse_dify_output error: {e}"
#         st.session_state["debug_parse_path"] = "error"
#         return []

def _parse_dify_output(resp: dict) -> List[Dict]:
    """
    Difyのレスポンスから質問リストを抽出。
    優先: data.outputs.q_list
      - q        -> text
      - score    -> priority（正規化なし）
      - tag/tags -> tags (list[str])
      - status   -> status（英語のまま: unanswered/on_hold/take_home/resolved）
    """
    try:
        outputs = (resp or {}).get("data", {}).get("outputs", {}) or {}
        q_list = outputs.get("q_list", [])
        out: List[Dict] = []

        valid_status = {"unanswered", "on_hold", "take_home", "resolved"}
        alias_map = {
            "pending": "unanswered", "open": "unanswered",
            "onhold": "on_hold", "hold": "on_hold",
            "takehome": "take_home",
            "answered": "resolved", "done": "resolved", "completed": "resolved",
        }

        for it in q_list:
            if not isinstance(it, dict):
                if isinstance(it, str) and it.strip():
                    out.append({"text": it.strip(), "priority": 50, "tags": [], "status": "unanswered"})
                continue

            text = (it.get("q") or it.get("text") or "").strip()
            if not text:
                continue

            score = it.get("score", 50)
            try:
                priority = float(score)
            except Exception:
                priority = 50.0

            tags = it.get("tag") or it.get("tags") or []
            if isinstance(tags, str):
                tags = [tags]
            elif not isinstance(tags, list):
                tags = []

            raw_status = (it.get("status") or "").strip().lower()
            status = alias_map.get(raw_status, raw_status)
            if status not in valid_status:
                status = "unanswered"

            out.append({"text": text, "priority": priority, "tags": tags, "status": status})

        # デバッグ
        st.session_state["debug_parse_path"] = "data.outputs.q_list"
        st.session_state["debug_parsed_count"] = len(out)
        st.session_state["debug_parsed_qs"] = out

        return out

    except Exception as e:
        st.session_state["dify_last_error"] = f"_parse_dify_output error: {e}"
        st.session_state["debug_parse_path"] = "error"
        return []


# ==============================
# 非同期 1 回実行
# ==============================
# def run_dify_once_async(trigger: str):
#     """
#     非暗転・非同期で 1 回だけ実行。完了後 +3 秒のクールダウン。
#     既存の質問リストにマージする
#     """
#     if dify_busy() or not dify_next_ok():
#         return

#     def _job():
#         try:
#             dify_mark_busy(True)
#             inputs = collect_inputs_for_dify()

#             # 実行前ログ
#             st.session_state["dify_status_log"] = st.session_state.get("dify_status_log", [])
#             _status(f"送信準備: base={_resolve_api_base()}, wf={st.session_state.get('dify_workflow_id','—')}, "
#                     f"mode={'streaming' if st.session_state.get('dify_streaming', True) else 'blocking'}")

#             st.session_state["dify_last_payload"] = inputs

#             rm = "streaming" if st.session_state.get("dify_streaming", True) else "blocking"
#             on_evt = _stream_event_logger if rm == "streaming" else None

#             t0 = time.monotonic()
#             resp = call_dify(inputs, response_mode=rm, on_event=on_evt)
#             dt = time.monotonic() - t0

#             st.session_state["dify_last_response"] = resp
#             st.session_state["dify_last_error"] = ""
#             st.session_state["dify_last_ran_at"] = datetime.now().strftime("%m/%d %H:%M:%S")
#             _status(f"完了: {dt:.1f}s")

#             # 最終レスポンスで確定反映（置換）
#             new_qs = _parse_dify_output(resp)

#             st.session_state["debug_parsed_qs"] = new_qs

#             if new_qs:
#                 st.session_state["questions"] = dedup_questions(new_qs, threshold=0.9)

#             # Streaming中に貯めた本文をデバッグ用に統合表示へ
#             if st.session_state.get("dify_partial_answer"):
#                 st.session_state["debug_combined_answer"] = (
#                     st.session_state.get("debug_combined_answer", "") + st.session_state["dify_partial_answer"]
#                 )
#                 st.session_state["dify_partial_answer"] = ""
            
#             # ==== ここで UI を再描画 ====
#             # add_script_run_ctx(t) 済みなのでスレッドから rerun してOK
#             try:
#                 st.session_state["__dify_last_update"] = time.monotonic()
#                 st.rerun()
#             except Exception:
#                 pass

#         except Exception as e:
#             st.session_state["dify_last_error"] = f"{type(e).__name__}: {e}"
#             _status(f"エラー: {type(e).__name__}: {e}")
#         finally:
#             dify_mark_busy(False)
#             dify_mark_next_after(3.0)

#     t = threading.Thread(target=_job, daemon=True, name=f"dify-job-{trigger}")
#     add_script_run_ctx(t)   # ←必須
#     t.start()

def run_dify_once_async(trigger: str):
    if dify_busy() or not dify_next_ok():
        return

    def _job():
        try:
            dify_mark_busy(True)
            inputs = collect_inputs_for_dify()
            st.session_state["dify_last_payload"] = inputs

            rm = "streaming" if st.session_state.get("dify_streaming", True) else "blocking"
            on_evt = _stream_event_logger if rm == "streaming" else None
            resp = call_dify(inputs, response_mode=rm, on_event=on_evt)

            st.session_state["dify_last_response"] = resp
            st.session_state["dify_last_error"] = ""
            st.session_state["dify_last_ran_at"] = datetime.now().strftime("%m/%d %H:%M:%S")

            # === ここで置換（マージしない） ===
            new_qs = _parse_dify_output(resp)  # ← status/priority/tags込みですでに整形
            st.session_state["debug_parsed_qs"] = new_qs
            if isinstance(new_qs, list):
                st.session_state["questions"] = new_qs
                st.session_state["questions_source"] = "dify"  # 重要：DBの再ロードで潰さないガード

        except Exception as e:
            st.session_state["dify_last_error"] = f"{type(e).__name__}: {e}"
        finally:
            dify_mark_busy(False)
            dify_mark_next_after(3.0)

    t = threading.Thread(target=_job, daemon=True, name=f"dify-job-{trigger}")
    add_script_run_ctx(t)
    t.start()


# ==============================
# キャッシュ（読み込み）
# ==============================
@st.cache_data(ttl=30, show_spinner=False)
def cached_list_customers():
    return dbsvc.list_customers(None)

@st.cache_data(ttl=30, show_spinner=False)
def cached_list_meetings(customer_id: Optional[str]):
    return dbsvc.list_meetings(None, customer_id)

@st.cache_data(ttl=15, show_spinner=False)
def cached_bundle(meeting_id: Optional[str]):
    return (
        dbsvc.get_meeting_bundle(None, meeting_id)
        if meeting_id
        else {"transcript": [], "questions": [], "notes": []}
    )

def clear_small_caches():
    cached_list_customers.clear()
    cached_list_meetings.clear()
    cached_bundle.clear()

# ==============================
# 初期ロード
# ==============================
if "initialized" not in st.session_state:
    st.session_state.initialized = True
    st.session_state.outbox = []   # 使うなら
    customers = cached_list_customers()
    st.session_state.customer_list = customers
    st.session_state.customer_id = customers[0]["id"] if customers else None
    meets = cached_list_meetings(st.session_state.customer_id) if st.session_state.customer_id else []
    st.session_state.meeting_list = meets
    st.session_state.meeting_id = meets[0]["id"] if meets else None

# def load_session_data():
#     bundle = cached_bundle(st.session_state.meeting_id)
#     profile = dbsvc.get_customer(None, st.session_state.customer_id) if st.session_state.customer_id else {}
#     st.session_state.profile = profile or {}
#     st.session_state.transcript = bundle["transcript"]
#     st.session_state.questions = bundle["questions"]
#     st.session_state.note_text = st.session_state.get("note_text", "")
#     if bundle["notes"]:
#         st.session_state.note_text = bundle["notes"][-1]["content"]

def load_session_data(force_db_reload: bool = False):
    bundle = cached_bundle(st.session_state.meeting_id)
    profile = dbsvc.get_customer(None, st.session_state.customer_id) if st.session_state.customer_id else {}
    st.session_state.profile = profile or {}
    st.session_state.transcript = bundle["transcript"]

    # メモは常にUIへ反映（最新ノートを上書き表示運用）
    st.session_state.note_text = st.session_state.get("note_text", "")
    if bundle["notes"]:
        st.session_state.note_text = bundle["notes"][-1]["content"]

    # meetingが変わった時はDBで初期化してOK
    changed_meeting = (st.session_state.get("_loaded_meeting_id") != st.session_state.meeting_id)

    # ここが重要：Difyで上書き済みなら、force指定かmeeting切り替え時以外はDBで潰さない
    if force_db_reload or changed_meeting or not st.session_state.get("questions"):
        st.session_state.questions = bundle["questions"]
        st.session_state["questions_source"] = "db"

    st.session_state["_loaded_meeting_id"] = st.session_state.meeting_id

load_session_data()

# セッション初期化直後あたりに
st.session_state.setdefault("questions_source", "db")  # "db" or "dify"
st.session_state.setdefault("_loaded_meeting_id", None)

# ==============================
# 小ユーティリティ（ローカル更新）
# ==============================
# def _to_int_priority(p):
#     if isinstance(p, (int, float)):
#         return int(round(float(p) * 100)) if float(p) <= 1.0 else int(p)
#     return 0

def _set_status(qid: str, new_status: str):
    for q in st.session_state.questions:
        if q.get("id") == qid or q.get("id") is None and q.get("text"):
            if q.get("id") == qid:
                q["status"] = new_status
                break

def _set_priority(qid: str, new_p100: int):
    for q in st.session_state.questions:
        if q.get("id") == qid:
            q["priority"] = new_p100
            break

def _all_tags(qs: List[Dict]) -> List[str]:
    tags = set()
    for q in qs:
        for t in (q.get("tags") or []):
            tags.add(t)
    return sorted(tags)

def _save_questions_to_db():
    with inline_status("🛰️ 質問をDBへ保存中…"):
        dbsvc.upsert_questions(None, st.session_state.meeting_id, st.session_state.questions)
        clear_small_caches()

def _save_note_to_db():
    with inline_status("🛰️ メモをDBへ保存中…"):
        dbsvc.add_note(None, st.session_state.meeting_id, st.session_state.note_text)
        clear_small_caches()

# ==============================
# セッション情報（更新/保存ボタン、Dify制御）
# ==============================
with st.container(border=True):
    c1, c2, c3, c4, c5 = st.columns([1.2, 1.2, 1.2, 0.9, 1.6])
    with c1:
        st.caption("セッション情報")
    with c2:
        customers = cached_list_customers()
        st.session_state.customer_list = customers
        if customers:
            idx = st.selectbox(
                "顧客",
                options=list(range(len(customers))),
                format_func=lambda i: customers[i]["name"],
                label_visibility="collapsed",
                key="sel_customer",
            )
            st.session_state.customer_id = customers[idx]["id"]
        else:
            st.caption("顧客なし")
    with c3:
        meets = cached_list_meetings(st.session_state.customer_id) if st.session_state.customer_id else []
        st.session_state.meeting_list = meets
        if meets:
            midx = st.selectbox(
                "商談",
                options=list(range(len(meets))),
                format_func=lambda i: f"{meets[i]['meeting_date']} / {meets[i]['title']}",
                label_visibility="collapsed",
                key="sel_meeting",
            )
            st.session_state.meeting_id = meets[midx]["id"]
        else:
            st.caption("商談なし")
    with c4:
        if st.button("更新", use_container_width=True):
            st.rerun()
        if st.button("DB保存", use_container_width=True):
            _save_note_to_db()
            _save_questions_to_db()

    with c5:
        colA, colB = st.columns(2)
        with colA:
            if st.button("▶ 開始", use_container_width=True, disabled=dify_busy()):
                st.session_state.meeting_started = True
                dify_mark_next_after(0.0)
                run_dify_once_async("start")
        with colB:
            if st.button("■ 終了", use_container_width=True):
                st.session_state.meeting_started = False
        status_txt = "Dify: 実行中…" if dify_busy() else "Dify: アイドル"
        nxt = max(0.0, st.session_state.get("dify_next_after", 0.0) - time.monotonic())
        last = st.session_state.get("dify_last_ran_at", "—")
        st.caption(f"{status_txt} / 最終: {last}") # / 次回まで: {nxt:.0f}s")

# 自動スケジューラ（開始中のみ）
if st.session_state.meeting_started:
    run_dify_once_async("tick")

# ==============================
# タブ
# ==============================
tab_assist, tab_trans, tab_backlog, tab_profile, tab_history, tab_dify = st.tabs(
    ["Assist（メモ×Top3×編集）", "Transcript（文字起こし）", "Backlog（取得状況）", "Lead Profile（DB保存）", "履歴 / DB", "Dify デバッグ"]
)

# ===== Assist
with tab_assist:
    left, right = st.columns([0.55, 0.45], gap="large")

    # --- メモ（ローカル編集 → 保存でDB）
    with left:
        st.subheader("📝 メモ（上書き保存）")
        st.session_state.note_text = st.text_area("1行=1要点で入力（Enterで改行）", height=260, value=st.session_state.get("note_text",""))
        c1, c2 = st.columns([1, 1])
        if c1.button("メモをDBへ保存", use_container_width=True, key="btn_save_note"):
            _save_note_to_db()
        st.caption("保存ボタンでDBへ上書き。未保存の変更は画面上だけに反映。")

    # --- Top3
    with right:
        st.subheader("🔥 今すぐ聞くべき3問")
        # st.session_state.questions = recompute_priorities(
        #     st.session_state.questions,
        #     stage=st.session_state.profile.get("stage", "初回"),
        #     temperature=0.5,
        #     profile=st.session_state.profile,
        #     transcript=[t for _, t in st.session_state.transcript[-30:]],
        # )
        candidates = [q for q in st.session_state.questions if q.get("status") not in ("resolved", "take_home")]
        top3 = sorted(
            candidates,
            key=lambda x: _to_int_priority(x.get("priority", 0)),
            reverse=True
            )[:3]

        st.markdown('<div class="top3">', unsafe_allow_html=True)
        cols = st.columns(3) if top3 else [st.container()]
        for i, q in enumerate(top3):
            qid = q.get("id") or f"tmp-top-{i}"
            with cols[i]:
                st.markdown('<div class="card">', unsafe_allow_html=True)
                st.markdown(f"#### #{i+1}")
                st.markdown(f'<div class="qtext">{q.get("text","")}</div>', unsafe_allow_html=True)
                tag_html = "".join([f'<span class="badge">#{t}</span>' for t in (q.get("tags") or [])])
                if tag_html:
                    st.markdown(tag_html, unsafe_allow_html=True)
                st.markdown(f"<div class='badge'>priority: {_to_int_priority(q.get('priority',0))}</div>", unsafe_allow_html=True)
                st.markdown('<div class="btnrow">', unsafe_allow_html=True)
                cta1, cta2, cta3 = st.columns(3)
                with cta1:
                    if st.button("✅ 聞けた", key=f"top3-ok-{qid}", use_container_width=True):
                        _set_status(qid, "resolved")
                with cta2:
                    if st.button("🧳 持ち帰り", key=f"top3-take-{qid}", use_container_width=True):
                        _set_status(qid, "take_home")
                with cta3:
                    if st.button("🕒 保留中", key=f"top3-hold-{qid}", use_container_width=True):
                        _set_status(qid, "on_hold")
                st.markdown("</div>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")

    # --- 質問リスト（ローカル編集→保存でDB） + タグ絞り込み
    # st.subheader("📋 質問リスト（ローカル編集 → 保存でDB同期）")
    # fc1, fc2, fc3 = st.columns([1.4, 1.2, 0.9])
    # with fc1:
    #     kw = st.text_input("キーワード", placeholder="例: 稟議 / 連携 / SAML", key="q_kw")
    # with fc2:
    #     all_tag_choices = _all_tags(st.session_state.questions)
    #     sel_tags = st.multiselect("タグで絞り込み", options=all_tag_choices, default=[], key="q_tag_filter")
    # with fc3:
    #     min_p = st.number_input("優先度≧", min_value=0, max_value=100, value=0, step=1, key="q_minp")

    st.subheader("📋 質問リスト（ローカル編集 → 保存でDB同期）")
    fc1, fc2, fc3, fc4 = st.columns([1.4, 1.2, 1.2, 0.9])
    with fc1:
        kw = st.text_input("キーワード", placeholder="例: 稟議 / 連携 / SAML", key="q_kw")
    with fc2:
        all_tag_choices = _all_tags(st.session_state.questions)
        sel_tags = st.multiselect("タグで絞り込み", options=all_tag_choices, default=[], key="q_tag_filter")
    with fc3:
        status_choices = ["(すべて)", "未取得", "保留中", "持ち帰り", "聞けた"]
        sel_status = st.selectbox("ステータスで絞り込み", status_choices, index=0)
    with fc4:
        min_p = st.number_input("優先度≧", min_value=0, max_value=100, value=0, step=1, key="q_minp")


    with st.container(border=True):
        ad1, ad2 = st.columns([0.75, 0.25])
        with ad1:
            new_txt = st.text_input("質問を追加（Enterで確定）", key="q_add_text", label_visibility="collapsed", placeholder="新しい質問を入力")
        with ad2:
            if st.button("追加", use_container_width=True, key="btn_add_question"):
                txt = (new_txt or "").strip()
                if txt:
                    st.session_state.questions.append(
                        {"id": None, "text": txt, "tags": [], "role": "—", "priority": 0.5, "status": "unanswered"}
                    )
                    st.session_state.questions = dedup_questions(st.session_state.questions, threshold=0.88)
                    st.session_state["q_add_text"] = ""

    # def _filter_for_list(qs: List[Dict]) -> List[Dict]:
    #     rows = [q for q in qs if q.get("status") not in ("resolved", "take_home")]
    #     if kw:
    #         rows = [q for q in rows if kw in q.get("text", "")]
    #     if sel_tags:
    #         rows = [q for q in rows if set(sel_tags).issubset(set(q.get("tags") or []))]
    #     rows = [q for q in rows if _to_int_priority(q.get("priority", 0)) >= min_p]
    #     return sorted(rows, key=lambda x: _to_int_priority(x.get("priority", 0)), reverse=True)

    def _filter_for_list(qs: List[Dict]) -> List[Dict]:
        rows = list(qs)
        # ステータス絞り込み
        if sel_status != "(すべて)":
            want_en = EN[sel_status]  # 既存のJP<->ENマップを使用
            rows = [q for q in rows if q.get("status") == want_en]

        # 既存のキーワード/タグ/優先度フィルタ
        if kw:
            rows = [q for q in rows if kw in q.get("text", "")]
        if sel_tags:
            rows = [q for q in rows if set(sel_tags).issubset(set(q.get("tags") or []))]
        rows = [q for q in rows if _to_int_priority(q.get("priority", 0)) >= min_p]

        # 表示順は priority 降順
        return sorted(rows, key=lambda x: _to_int_priority(x.get("priority", 0)), reverse=True)

    view_rows = _filter_for_list(st.session_state.questions)
    st.caption(f"該当 {len(view_rows)} 件")

    for i, q in enumerate(view_rows):
        qid = q.get("id") or f"tmp-{i}"
        with st.container():
            st.markdown('<div class="row-compact">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([0.64, 0.16, 0.20])
            with c1:
                st.markdown(f"**{q.get('text','')}**")
                if q.get("tags"):
                    st.markdown(" ".join([f'<span class="badge">#{t}</span>' for t in q["tags"]]), unsafe_allow_html=True)
            with c2:
                p_now = _to_int_priority(q.get("priority", 0))
                p_new = st.number_input("priority", min_value=0, max_value=100, step=1, value=p_now, key=f"row-pr-{qid}")
                if p_new != p_now:
                    _set_priority(qid, p_new)
            with c3:
                prev_en = q.get("status", "unanswered")
                prev_jp = JP.get(prev_en, "未取得")
                sel_jp = st.selectbox("ステータス", JP_ORDER, index=JP_ORDER.index(prev_jp), key=f"row-st-{qid}")
                new_en = EN[sel_jp]
                if new_en != prev_en:
                    _set_status(qid, new_en)
            st.markdown("</div>", unsafe_allow_html=True)

    csave1, csave2 = st.columns(2)
    if csave1.button("質問の変更をDBへ保存（上）", type="primary", use_container_width=True, key="btn_sync_top"):
        _save_questions_to_db()
    if csave2.button("質問の変更をDBへ保存（下）", use_container_width=True, key="btn_sync_bottom"):
        _save_questions_to_db()

# ===== Transcript
with tab_trans:
    st.subheader("会話ログ（チャット表示）")
    c1, c2, c3 = st.columns([1.2, 0.8, 0.8])
    keyword = c1.text_input("キーワード検索（例：SAML / 予算）", key="kw_trans")
    limit = c2.slider("表示件数", 10, 300, 120, 10, key="log_limit")
    as_table = c3.toggle("テーブル表示", key="log_table")
    logs = st.session_state.transcript[-limit:]
    if keyword:
        logs = [x for x in logs if keyword in x[1]]
    if as_table:
        df = pd.DataFrame(logs, columns=["time", "utterance"])
        st.dataframe(df, use_container_width=True, height=560)
    else:
        for i, (ts, text) in enumerate(logs):
            role = "assistant" if i % 2 == 0 else "user"
            with st.chat_message(role):
                st.markdown(f"**{ts}**  \n{text}")

    st.divider()
    new_line = st.text_input("新しい発話を追加（例：稟議は部長決裁です）", key="asr_line", value="")
    add_col, save_col = st.columns(2)
    if add_col.button("発話を追加（セッション）", type="primary", key="btn_add_line"):
        if new_line.strip():
            st.session_state.transcript.append((datetime.now().strftime("%H:%M:%S"), new_line.strip()))
            st.toast("発話をセッションに追加しました")
    if save_col.button("直近発話をDB保存", key="btn_line_to_db"):
        if st.session_state.transcript:
            ts, text = st.session_state.transcript[-1]
            with inline_status("🛰️ 直近発話をDBへ保存中…"):
                dbsvc.add_transcript_line(None, st.session_state.meeting_id, ts, "sales", text)
                clear_small_caches()
                st.success("直近の発話をDBへ保存しました")

# ===== Backlog
with tab_backlog:
    st.subheader("取得状況まとめ（Top/リストから除外したもの）")

    def _jp_rows(rows: List[Dict]) -> List[Dict]:
        return [
            {
                "id": r.get("id"),
                "質問": r.get("text", ""),
                "status": JP.get(r.get("status", "unanswered"), "未取得"),
                "priority": _to_int_priority(r.get("priority", 0)),
                "tags": " / ".join(r.get("tags") or []),
            }
            for r in rows
        ]

    pending = [q for q in st.session_state.questions if q.get("status") == "unanswered"]
    resolved = [q for q in st.session_state.questions if q.get("status") == "resolved"]
    on_hold = [q for q in st.session_state.questions if q.get("status") == "on_hold"]
    take_home = [q for q in st.session_state.questions if q.get("status") == "take_home"]

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"### 🕒 保留中 — {len(on_hold)}件")
        st.dataframe(pd.DataFrame(_jp_rows(on_hold)), use_container_width=True, height=260)
        st.markdown(f"### 🧳 持ち帰り — {len(take_home)}件")
        st.dataframe(pd.DataFrame(_jp_rows(take_home)), use_container_width=True, height=260)
    with c2:
        st.markdown(f"### ✅ 聞けた — {len(resolved)}件")
        st.dataframe(pd.DataFrame(_jp_rows(resolved)), use_container_width=True, height=260)
        st.markdown(f"### ❗ 未取得 — {len(pending)}件")
        st.dataframe(pd.DataFrame(_jp_rows(pending)), use_container_width=True, height=260)

# ===== Profile
with tab_profile:
    st.subheader("顧客・案件プロフィール（DB保存）")
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("会社名", value=st.session_state.profile.get("name", ""), key="pf_name")
        industry = st.text_input("業種", value=st.session_state.profile.get("industry", ""), key="pf_industry")
        size = st.selectbox(
            "規模",
            ["~100名", "100-500名", "500-1000名", "1000名~"],
            index=(
                ["~100名", "100-500名", "500-1000名", "1000名~"].index(st.session_state.profile.get("size", "100-500名"))
                if st.session_state.profile.get("size") in ["~100名", "100-500名", "500-1000名", "1000名~"]
                else 1
            ),
            key="pf_size",
        )
        usecase = st.text_input("想定用途（例：見積自動化）", value=st.session_state.profile.get("usecase", ""), key="pf_usecase")
    with col2:
        kpi = st.text_input("最重要KPI（例：工数削減）", value=st.session_state.profile.get("kpi", ""), key="pf_kpi")
        budget_upper = st.text_input("稟議上限額（例：300万円）", value=st.session_state.profile.get("budget_upper", ""), key="pf_budget")
        deadline = st.text_input("希望導入時期（例：2025/12）", value=st.session_state.profile.get("deadline", ""), key="pf_deadline")
        constraints = st.text_input("制約（例：SaaSのみ/持出禁止）", value=st.session_state.profile.get("constraints", ""), key="pf_constraints")
    stage = st.selectbox("商談フェーズ（メモ用・DB未保存）", ["初回", "要件定義", "見積・稟議", "クロージング"], key="pf_stage")

    if st.button("顧客情報をDB保存", key="btn_save_profile"):
        with inline_status("🛰️ 顧客情報を保存中…"):
            payload = {
                "id": st.session_state.customer_id,
                "name": name,
                "industry": industry,
                "size": size,
                "usecase": usecase,
                "kpi": kpi,
                "budget_upper": budget_upper,
                "deadline": deadline,
                "constraints": constraints,
            }
            cid = dbsvc.upsert_customer(None, payload)
            st.session_state.customer_id = cid

# ===== History
with tab_history:
    st.subheader("過去の商談（この顧客名に紐付く会話）")
    meetings = cached_list_meetings(st.session_state.customer_id) if st.session_state.customer_id else []
    st.dataframe(pd.DataFrame(meetings), use_container_width=True, height=300)
    st.caption("※ conversations.customer_id が無い環境でも customers.name と customer_company の一致で紐付けています。")

# ===== Dify デバッグ（強化版）
with tab_dify:
    st.subheader("🔧 Dify デバッグ（強化）")
    c1, c2, c3, c4 = st.columns([0.9, 0.9, 0.9, 1.3])
    with c1:
        if st.button("▶ 手動実行", use_container_width=True, disabled=dify_busy()):
            dify_mark_next_after(0.0)
            run_dify_once_async("manual")
    with c2:
        if st.button("⟳ クールダウン解除", use_container_width=True):
            dify_mark_next_after(0.0)
    with c3:
        if st.button("🧹 ログ消去", use_container_width=True):
            st.session_state["dify_status_log"] = []
            st.session_state["dify_partial_outputs"] = []
            st.session_state["debug_combined_answer"] = ""
    with c4:
        st.caption("実行中: " + ("YES" if dify_busy() else "NO"))

    st.markdown("##### 現在の設定スナップショット")
    st.code(json.dumps({
        "api_base": _resolve_api_base(),
        "api_key": _mask(st.session_state.get("dify_api_key","")),
        "endpoint_type": st.session_state.get("dify_endpoint_type","workflow"),
        "workflow_id": st.session_state.get("dify_workflow_id",""),
        "mode": "streaming" if st.session_state.get("dify_streaming", True) else "blocking",
    }, ensure_ascii=False, indent=2))

    st.markdown("##### ステータスログ（最新50）")
    tail = st.session_state.get("dify_status_log", [])[-50:]
    st.code("\n".join(tail) if tail else "—")

    st.markdown("##### 最後に送信した inputs")
    st.code(json.dumps(st.session_state.get("dify_last_payload", {}), ensure_ascii=False, indent=2))

    st.markdown("##### 最後のレスポンス（生）")
    st.code(json.dumps(st.session_state.get("dify_last_response", {}), ensure_ascii=False, indent=2))

    st.caption("パース後の質問リスト")
    st.code(json.dumps(st.session_state.get("debug_parsed_qs", []), ensure_ascii=False, indent=2))


    if st.session_state.get("dify_partial_outputs"):
        st.markdown("##### Streaming途中の一時的な出力（questions_json）")
        st.code(json.dumps(st.session_state.get("dify_partial_outputs", []), ensure_ascii=False, indent=2))

    if st.session_state.get("debug_combined_answer"):
        st.markdown("##### Streamingで受けた回答断片の結合")
        st.text_area("combined answer", value=st.session_state["debug_combined_answer"], height=160)

    if st.session_state.get("dify_last_error"):
        st.error(st.session_state["dify_last_error"])
