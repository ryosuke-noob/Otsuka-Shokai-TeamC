# ui/profile_tab.py
import streamlit as st
from services import supabase_db as dbsvc
import pandas as pd
import state

def render_profile_tab():
    st.subheader("顧客・案件プロフィール")
    profile = st.session_state.get("profile", {})
    
    payload = {
        "id": st.session_state.get("customer_id"),
        "name": st.text_input("会社名", value=profile.get("name", "")),
        "industry": st.text_input("業種", value=profile.get("industry", "")),
        "size": st.selectbox("規模", ["~100名", "100-500名", "500-1000名", "1000名~"],
            index=["~100名", "100-500名", "500-1000名", "1000名~"].index(profile.get("size")) if profile.get("size") in ["~100名", "100-500名", "500-1000名", "1000名~"] else 0
        ),
        "usecase": st.text_input("想定用途", value=profile.get("usecase", "")),
        "kpi": st.text_input("重要KPI", value=profile.get("kpi", "")),
        "budget_upper": st.text_input("稟議上限額", value=profile.get("budget_upper", "")),
        "deadline": st.text_input("希望導入時期", value=profile.get("deadline", "")),
        "constraints": st.text_input("制約", value=profile.get("constraints", "")),
    }

    if st.button("顧客情報をDB保存", type="primary"):
        cid = dbsvc.upsert_customer(None, payload)
        st.session_state.customer_id = cid
        st.toast("保存しました")

def render_history_tab():
    st.subheader("過去の商談履歴")
    meetings = state.cached_list_meetings(st.session_state.customer_id)
    st.dataframe(pd.DataFrame(meetings), use_container_width=True)