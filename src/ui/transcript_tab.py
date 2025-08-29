# ui/transcript_tab.py
import streamlit as st
import pandas as pd
from datetime import datetime
import state
from services import supabase_db as dbsvc

def render_transcript_tab():
    st.subheader("会話ログ")
    
    logs = st.session_state.get("transcript", [])
    df = pd.DataFrame(logs, columns=["Time", "Utterance"])
    st.dataframe(df, use_container_width=True, height=500)

    st.divider()
    new_line = st.text_input("発話を追加")
    if st.button("追加してDB保存", disabled=not new_line):
        ts = datetime.now().strftime("%H:%M:%S")
        dbsvc.add_transcript_line(None, st.session_state.meeting_id, ts, "manual", new_line)
        state.clear_small_caches()
        st.rerun()