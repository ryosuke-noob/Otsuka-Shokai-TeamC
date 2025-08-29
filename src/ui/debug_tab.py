# ui/debug_tab.py
import json
import streamlit as st
from services import dify_service

def render_debug_tab():
    st.subheader("🔧 Dify デバッグ")
    
    if st.button("手動実行", disabled=dify_service.dify_busy()):
        dify_service.run_dify_once_async("manual_debug")

    with st.expander("ステータスログ"):
        st.code("\n".join(st.session_state.get("dify_status_log", [])), height=200)

    with st.expander("最終送信 payload"):
        st.json(st.session_state.get("dify_last_payload", {}))

    with st.expander("最終受信 response"):
        st.json(st.session_state.get("dify_last_response", {}))

    with st.expander("パース後の質問リスト"):
        st.json(st.session_state.get("debug_parsed_qs", []))

    if err := st.session_state.get("dify_last_error"):
        st.error(err)