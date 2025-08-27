# app.py
from __future__ import annotations
import os
import streamlit as st
from dotenv import load_dotenv

# --- モジュールのインポート ---
# `app_src`というプレフィックスは不要なため削除し、直接インポートします。
from services import supabase_db as dbsvc
from services import dify_service
import state
from ui import (
    sidebar, header, assist_tab, transcript_tab,
    backlog_tab, profile_tab, history_tab, debug_tab
)

# ==============================
# 基本設定
# ==============================
load_dotenv()
st.set_page_config(page_title="Sales Live Assist v3.3 (Modular)", layout="wide")

if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_ANON_KEY"):
    st.error("環境変数 SUPABASE_URL / SUPABASE_ANON_KEY (.env) が未設定です。")
    st.stop()

# ==============================
# スタイル定義
# ==============================
st.markdown(
    """
<style>
div[data-testid="stVerticalBlockBorderWrapper"] {
    margin-bottom: 1rem; /* 16pxの余白を追加 */
}
:root { --top-safe-area: 52px; }
.block-container { padding-top: calc(var(--top-safe-area) + .2rem) !important; }
[data-testid="stModal"], [data-testid="stDialogOverlay"], div[role="dialog"], div[role="alertdialog"], div[aria-modal="true"] {
  background: transparent !important; backdrop-filter: none !important; }
[data-testid="stModal"] > div, div[role="dialog"] > div { box-shadow: none !important; }
.stSpinner, .stStatus { background: transparent !important; }
.badge { display:inline-block; padding:2px 6px; font-size:.8rem; border-radius:999px; border:1px solid rgba(255,255,255,.12); margin-right:.35rem; opacity:.85; }
.top3 .card { border:1px solid rgba(255,255,255,.09); background:rgba(255,255,255,.03); border-radius:16px; padding:12px; height:100%; }
.top3 h4 { margin:.2rem 0 .4rem 0; font-weight:800; }
.top3 .qtext { font-size:1.05rem; line-height:1.55rem; margin:.25rem 0 .5rem 0; }
.top3 .btnrow { display:grid; grid-template-columns:repeat(3,1fr); gap:.5rem; }
.top3 div[data-testid="stButton"] > button {
  border-radius:999px !important; border:1px solid rgba(255,255,255,.12); background:rgba(255,255,255,.04);
  height:44px; white-space:nowrap; padding:.4rem .6rem !important;
}
.row-compact { padding:.55rem .6rem; border:1px solid rgba(255,255,255,.08); border-radius:12px; }
</style>
""",
    unsafe_allow_html=True,
)

# ==============================
# メイン処理
# ==============================
def main():
    # --- 初期化 ---
    dbsvc.init_db(None)
    dbsvc.seed_if_empty(None, None)
    state.initialize_session()
    dify_service._init_dify_debug_state()
    state.load_session_data()

    # --- UI描画 ---
    sidebar.render_sidebar()
    header.render_header()

    # --- 自動実行スケジューラ ---
    if st.session_state.get("meeting_started", False):
        dify_service.run_dify_once_async("tick")

    # --- タブ定義 ---
    tab_names = ["Assist", "Transcript", "Backlog", "Lead Profile", "履歴", "Dify デバッグ"]
    tab_assist, tab_trans, tab_backlog, tab_profile, tab_history, tab_dify = st.tabs(tab_names)

    with tab_assist:
        assist_tab.render_assist_tab()
    with tab_trans:
        transcript_tab.render_transcript_tab()
    with tab_backlog:
        backlog_tab.render_backlog_tab()
    with tab_profile:
        profile_tab.render_profile_tab()
    with tab_history:
        history_tab.render_history_tab()
    with tab_dify:
        debug_tab.render_debug_tab()

if __name__ == "__main__":
    main()