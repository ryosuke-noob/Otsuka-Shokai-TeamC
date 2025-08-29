from __future__ import annotations
from typing import List, Dict, Any, Tuple
import streamlit as st
from app_src.services import supabase_db as dbsvc

def _status_options():
    return ["unanswered","answered","on_hold","take_home","resolved"]

def render_questions_panel(questions: List[Dict[str,Any]], *, backlog: List[Dict[str,Any]], on_hold: List[Dict[str,Any]], meeting_id=None) -> Tuple[List[Dict[str,Any]], List[Dict[str,Any]], List[Dict[str,Any]]]:
    # 追加UI
    with st.container(border=True):
        new_q = st.text_input("質問を追加（Enterで確定）", key="__q_add__")
        if st.button("追加", use_container_width=True):
            if new_q.strip():
                questions.append({"id": None, "text": new_q.strip(), "tags": [], "role":"—", "priority": 0.5, "status":"unanswered", "source":"ui"})
                dbsvc.upsert_questions(None, meeting_id, questions)
                st.success("質問を追加しました")
                st.experimental_rerun()

    # 一覧（簡易編集）
    for q in questions:
        with st.container(border=True):
            st.write(q.get("text",""))
            cols = st.columns([1,1,2])
            with cols[0]:
                pri = st.slider("priority", 0, 100, int(round(float(q.get("priority",0.5))*100)), key=f"pri_{q.get('id') or id(q)}")
            with cols[1]:
                stt = st.selectbox("status", _status_options(), index=_status_options().index(q.get("status","unanswered")), key=f"st_{q.get('id') or id(q)}")
            with cols[2]:
                if st.button("保存", key=f"save_{q.get('id') or id(q)}"):
                    q["priority"] = pri/100.0
                    q["status"] = stt
                    dbsvc.upsert_questions(None, meeting_id, [q])
                    st.toast("保存しました")

    backlog = [q for q in questions if q.get("status")=="take_home"]
    on_hold = [q for q in questions if q.get("status")=="on_hold"]
    return questions, backlog, on_hold
