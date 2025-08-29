# ui/backlog_tab.py
import streamlit as st
import pandas as pd
from typing import List, Dict
import utils

def render_backlog_tab():
    st.subheader("取得状況まとめ")

    def to_df_row(q: Dict) -> Dict:
        return {
            "質問": q.get("text", ""),
            "優先度": int(q.get("priority", 0.5) * 100),
            "タグ": ", ".join(q.get("tags", []))
        }

    qs = st.session_state.get("questions", [])
    status_map = {
        "resolved": ("✅ 聞けた", [q for q in qs if q.get("status") == "resolved"]),
        "take_home": ("🧳 持ち帰り", [q for q in qs if q.get("status") == "take_home"]),
        "on_hold": ("🕒 保留中", [q for q in qs if q.get("status") == "on_hold"]),
        "unanswered": ("❗ 未取得", [q for q in qs if q.get("status") == "unanswered"]),
    }

    for title, data in status_map.values():
        st.markdown(f"### {title} ({len(data)}件)")
        df = pd.DataFrame([to_df_row(q) for q in data])
        st.dataframe(df, use_container_width=True)