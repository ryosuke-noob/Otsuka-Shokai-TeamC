# ui/header.py
import streamlit as st
import state
from services import dify_service

def render_header():
    with st.container(border=True):
        c1, c2, c3, c4, c5 = st.columns([1.2, 1.2, 1.2, 0.9, 1.6])
        with c1: st.caption("セッション情報")
        with c2:
            customers = state.cached_list_customers()
            if customers:
                names = [c["name"] for c in customers]
                try:
                    current_name = [c['name'] for c in customers if c['id'] == st.session_state.customer_id][0]
                    idx = names.index(current_name)
                except (ValueError, IndexError):
                    idx = 0
                
                sel_name = st.selectbox("顧客", names, index=idx, label_visibility="collapsed")
                st.session_state.customer_id = [c['id'] for c in customers if c['name'] == sel_name][0]

        with c3:
            meets = state.cached_list_meetings(st.session_state.customer_id)
            if meets:
                titles = [f"{m['meeting_date']} / {m['title']}" for m in meets]
                try:
                    current_title = [t for m, t in zip(meets, titles) if m['id'] == st.session_state.meeting_id][0]
                    idx = titles.index(current_title)
                except (ValueError, IndexError):
                    idx = 0

                sel_title = st.selectbox("商談", titles, index=idx, label_visibility="collapsed")
                st.session_state.meeting_id = [m['id'] for m, t in zip(meets, titles) if t == sel_title][0]

        with c4:
            if st.button("更新", use_container_width=True): st.rerun()
            if st.button("DB保存", use_container_width=True):
                state._save_note_to_db()
                state._save_questions_to_db()
        
        with c5:
            colA, colB = st.columns(2)
            if colA.button(
                "▶ 開始",
                use_container_width=True,
                disabled=(dify_service.dify_busy() or st.session_state.get("meeting_started", False)),
            ):
                st.session_state.meeting_started = True
                dify_service.run_dify_once_async("start")
                st.rerun()
            if colB.button(
                "■ 終了",
                use_container_width=True,
                disabled=not st.session_state.get("meeting_started", False),
            ):
                st.session_state.meeting_started = False
                st.rerun()
            
            status = "実行中..." if dify_service.dify_busy() else "待機中"
            st.caption(f"Dify: {status} (最終実行: {st.session_state.dify_last_ran_at})")