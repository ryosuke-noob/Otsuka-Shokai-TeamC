from __future__ import annotations
from typing import List, Dict, Any
import streamlit as st

def render_top3(top3: List[Dict[str,Any]]) -> None:
    if not top3:
        st.caption("Top3 はまだありません")
        return
    cols = st.columns(len(top3))
    for i, q in enumerate(top3):
        with cols[i]:
            with st.container(border=True):
                st.markdown(f"#### #{i+1}")
                st.write(q.get("text","(no text)"))
                st.caption(f"priority: {q.get('priority',0):.2f} / status: {q.get('status','')}")
