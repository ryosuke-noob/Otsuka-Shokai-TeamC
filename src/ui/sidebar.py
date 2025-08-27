# ui/sidebar.py
import streamlit as st

def render_sidebar():
    with st.sidebar:
        st.header("⚙️ Dify 設定")
        st.session_state.dify_api_base = st.text_input(
            "API Base", value=st.session_state.dify_api_base
        )
        st.session_state.dify_api_key = st.text_input(
            "API Key", value=st.session_state.dify_api_key, type="password"
        )
        st.session_state.dify_endpoint_type = st.selectbox(
            "エンドポイント種別", ["workflow", "chat"],
            index=["workflow", "chat"].index(st.session_state.dify_endpoint_type)
        )
        st.session_state.dify_workflow_id = st.text_input(
            "Workflow ID", value=st.session_state.dify_workflow_id
        )
        st.session_state.dify_streaming = st.toggle(
            "Streamingモード", value=st.session_state.dify_streaming
        )