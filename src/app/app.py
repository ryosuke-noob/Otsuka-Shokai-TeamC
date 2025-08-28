from __future__ import annotations
import os
import streamlit as st
from dotenv import load_dotenv
from streamlit_webrtc import webrtc_streamer, WebRtcMode

# --- モジュールのインポート ---
# `app_src`というプレフィックスは不要なため削除し、直接インポートします。
from services import supabase_db as dbsvc
from services import dify_service
import state
from ui import (
    sidebar, header, assist_tab, transcript_tab,
    backlog_tab, profile_tab, history_tab, debug_tab
)
from services.asr import ASRService, SharedTranscript, load_whisper, DESIRED_BROWSER_SR
from services.summary import SummaryService, load_llm_client

# ==============================
# 基本設定
# ==============================
load_dotenv()
st.set_page_config(page_title="Sales Live Assist v3.3 (Modular)", layout="wide")

# --- env check ---
if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_ANON_KEY"):
    st.error("環境変数 SUPABASE_URL / SUPABASE_ANON_KEY を .env に設定してください。")
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
div[data-testid="stWebrtcStatus"] button,
div[data-testid="stWebrtcStatus"] + div button { display:none !important; }
</style>
""",
    unsafe_allow_html=True,
)

# ==============================
# メイン処理
# ==============================
def main():
    print("test")
    # --- 初期化 ---
    dbsvc.init_db(None)
    dbsvc.seed_if_empty(None, None)
    state.initialize_session()
    dify_service._init_dify_debug_state()
    state.load_session_data()

    shared: SharedTranscript = st.session_state.get("shared_tr") or SharedTranscript()
    st.session_state["shared_tr"] = shared

    whisper_model = load_whisper()
    llm_client, llm_model_name = load_llm_client()
    asr: ASRService = st.session_state.get("asr") or ASRService(
        whisper_model=whisper_model,
        segment_sink=shared.append_lines,
    )
    st.session_state["asr"] = asr

    summarizer: SummaryService = st.session_state.get("sum") or SummaryService(
        client=llm_client,
        model_name=llm_model_name,
    )
    st.session_state["sum"] = summarizer

    # --- WebRTC 起動（SENDONLY） ---
    ctx = webrtc_streamer(
        key=f"rtc",
        mode=WebRtcMode.SENDONLY,
        media_stream_constraints={
            "audio": {
                "channelCount": 1,
                "sampleRate": DESIRED_BROWSER_SR,
                "echoCancellation": False,
                "noiseSuppression": False,
                "autoGainControl": False,
            },
            "video": False,
        },
        audio_frame_callback=asr.audio_frame_callback,
        async_processing=True,
        desired_playing_state=bool(st.session_state.get("meeting_started", False)),
    )
    

    # --- UI描画 ---
    sidebar.render_sidebar()
    header.render_header()

    rtc_playing = bool(ctx and getattr(ctx.state, "playing", False))
    asr_running = st.session_state.get("asr_running", False)
    sum_running = st.session_state.get("sum_running", False)

    if rtc_playing:
        if not asr_running:
            asr.start()
            st.session_state["asr_running"] = True
        if not sum_running:
            summarizer.start(transcript_getter=shared.get, tick_q=asr.tick_q)
            st.session_state["sum_running"] = True
    else:
        if asr_running:
            asr.stop()
            st.session_state["asr_running"] = False
        if sum_running:
            summarizer.stop()
            st.session_state["sum_running"] = False
    # --- 自動実行スケジューラ ---
    if st.session_state.get("meeting_started", False):
        dify_service.run_dify_once_async("tick")

    # --- タブ定義 ---
    st.session_state["transcript_text"] = shared.get()
    st.session_state["summary_markdown"] = summarizer.summary_markdown()
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
