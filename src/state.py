# state.py
from __future__ import annotations
from typing import Optional
import streamlit as st
from services import supabase_db as dbsvc
from utils import inline_status

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
def initialize_session():
    if "initialized" not in st.session_state:
        st.session_state.initialized = True
        customers = cached_list_customers()
        st.session_state.customer_list = customers
        st.session_state.customer_id = customers[0]["id"] if customers else None
        meets = cached_list_meetings(st.session_state.customer_id)
        st.session_state.meeting_list = meets
        st.session_state.meeting_id = meets[0]["id"] if meets else None
        st.session_state.setdefault("questions_source", "db")
        st.session_state.setdefault("_loaded_meeting_id", None)

def load_session_data(force_db_reload: bool = False):
    meeting_id = st.session_state.get("meeting_id")
    customer_id = st.session_state.get("customer_id")

    bundle = cached_bundle(meeting_id)
    profile = dbsvc.get_customer(None, customer_id) if customer_id else {}
    st.session_state.profile = profile or {}
    st.session_state.transcript = bundle.get("transcript", [])

    st.session_state.note_text = st.session_state.get("note_text", "")
    notes = bundle.get("notes", [])
    if notes:
        st.session_state.note_text = notes[-1].get("content", "")

    changed_meeting = st.session_state.get("_loaded_meeting_id") != meeting_id

    if force_db_reload or changed_meeting or not st.session_state.get("questions"):
        st.session_state.questions = bundle.get("questions", [])
        st.session_state["questions_source"] = "db"

    st.session_state["_loaded_meeting_id"] = meeting_id

# ==============================
# 状態更新ヘルパー
# ==============================
def _set_status(qid: str, new_status: str):
    for q in st.session_state.get("questions", []):
        if q.get("id") == qid:
            q["status"] = new_status
            break

def _set_priority(qid: str, new_p100: int):
    for q in st.session_state.get("questions", []):
        if q.get("id") == qid:
            q["priority"] = new_p100 / 100.0
            break

def _save_questions_to_db():
    meeting_id = st.session_state.get("meeting_id")
    questions = st.session_state.get("questions", [])
    if meeting_id and questions:
        with inline_status("🛰️ 質問をDBへ保存中…"):
            dbsvc.upsert_questions(None, meeting_id, questions)
            clear_small_caches()

def _save_note_to_db():
    meeting_id = st.session_state.get("meeting_id")
    note_text = st.session_state.get("note_text", "")
    if meeting_id:
        with inline_status("🛰️ メモをDBへ保存中…"):
            dbsvc.add_note(None, meeting_id, note_text)
            clear_small_caches()