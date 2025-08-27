from __future__ import annotations
import os, time, queue
from typing import Optional

import numpy as np
import streamlit as st
from streamlit_webrtc import webrtc_streamer, WebRtcMode
from dotenv import load_dotenv

from ..services.asr import ASRService
from ..services.summary import SummaryService

ASR_SR    = 16000
CHUNK_SEC = 30.0
STEP_SEC  = 10.0
SAFE_TAIL = 0.5
SEMITONES = 12                      # +12 半音 → 2倍速
SPEED     = float(2 ** (SEMITONES/12.0))
LANG      = "ja"
FP16      = False
DESIRED_BROWSER_SR = 48000

OVERLAP_CHARS      = 900
TAIL_LINES_FOR_LLM = 24

AZURE_API_VERSION  = os.getenv("AZURE_OPENAI_API_VERSION", "2025-03-01-preview")
AZURE_CHAT_MODEL   = os.getenv("AZURE_OPENAI_CHAT_MODEL", "gpt-5-mini")


import threading
class SharedTranscript:
    def __init__(self):
        self._lock = threading.Lock()
        self._buf: list[str] = []
    def append_lines(self, segs: list[str]):
        if not segs: return
        with self._lock:
            for s in segs:
                if s:
                    self._buf.append(s + "\n")
    def get(self) -> str:
        with self._lock:
            return "".join(self._buf)

# =========================
# モデル/クライアントのロード
# =========================
@st.cache_resource(show_spinner=False)
def _load_whisper():
    import whisper
    return whisper.load_model("turbo")   # 既定は turbo

@st.cache_resource(show_spinner=False)
def _load_llm_client():
    load_dotenv('../../../.env')  # プロジェクト配置に合わせて調整
    from openai import AzureOpenAI
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key  = os.getenv("AZURE_OPENAI_API_KEY")
    if not endpoint or not api_key:
        st.warning("Azure OpenAI の環境変数(AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY)が未設定です。")
    client = AzureOpenAI(api_version=AZURE_API_VERSION,
                         azure_endpoint=endpoint,
                         api_key=api_key)
    return client, AZURE_CHAT_MODEL


# =========================
# メイン UI
# =========================
def render_whisper_page(dbsvc=None, meeting_id: Optional[str] = None):
    key = str(meeting_id or "default")

    # --- 共有テキスト（UI側） ---
    shared: SharedTranscript = st.session_state.get(f"shared_tr:{key}") or SharedTranscript()
    st.session_state[f"shared_tr:{key}"] = shared

    # --- モデル/クライアント ---
    whisper_model = _load_whisper()
    llm_client, llm_model_name = _load_llm_client()

    # --- サービスの初期化（初回のみ） ---
    asr: ASRService = st.session_state.get(f"asr:{key}") or ASRService(
        meeting_key=key,
        whisper_model=whisper_model,
        asr_sr=ASR_SR,
        chunk_sec=CHUNK_SEC,
        step_sec=STEP_SEC,
        safe_tail=SAFE_TAIL,
        speed=SPEED,
        lang=LANG,
        fp16=FP16,
        desired_browser_sr=DESIRED_BROWSER_SR,
    )
    st.session_state[f"asr:{key}"] = asr

    summarizer: SummaryService = st.session_state.get(f"sum:{key}") or SummaryService(
        meeting_key=key,
        client=llm_client,
        model_name=llm_model_name,
        overlap_chars=OVERLAP_CHARS,
        tail_lines_for_llm=TAIL_LINES_FOR_LLM,
    )
    st.session_state[f"sum:{key}"] = summarizer

    # --- WebRTC 起動（SENDONLY） ---
    ctx = webrtc_streamer(
        key=f"{key}_rtc",
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
    )

    # --- Start / Stop 管理 ---
    running_key = f"running:{key}"
    running = st.session_state.get(running_key, False)

    if bool(ctx and ctx.state.playing) and not running:
        asr.start()
        summarizer.start(transcript_getter=shared.get, tick_q=asr.tick_q)
        st.session_state[running_key] = True

    if st.session_state.get(running_key, False) and not bool(ctx and ctx.state.playing):
        asr.stop()
        summarizer.stop()
        st.session_state[running_key] = False

    # =========================
    # レイアウト
    # =========================
    st.subheader("Live Transcription & Summary（このタブだけ更新）")
    col_t, col_s = st.columns(2, gap="large")

    with col_t:
        st.markdown("#### 文字起こし")
        ph_transcript = st.empty()
        ph_transcript.text_area("Transcript", value=shared.get(), height=420)

    with col_s:
        st.markdown("#### 要約（営業向け・時系列）")
        ph_summary = st.empty()
        ph_summary.markdown(summarizer.summary_markdown())

    # --- 簡易ポーリングで UI を更新（このタブのみ） ---
    last_hb = time.time()
    try:
        last_hb = asr.hb_q.get_nowait()
    except queue.Empty:
        pass

    while bool(ctx and ctx.state.playing):
        # 新規セグメントを取り込み
        segs = asr.drain_segments()
        if segs:
            shared.append_lines(segs)
            ph_transcript.text_area("Transcript", value=shared.get(), height=420)
        # 要約はサービス側で更新済み
        ph_summary.markdown(summarizer.summary_markdown())

        # ハートビート監視（音声停止で抜ける）
        try:
            last_hb = asr.hb_q.get_nowait()
        except queue.Empty:
            pass
        if time.time() - last_hb > 2.0:
            break

        time.sleep(0.5)

    # --- 停止検知（再掲） ---
    if st.session_state.get(running_key, False) and not bool(ctx and ctx.state.playing):
        asr.stop()
        summarizer.stop()
        st.session_state[running_key] = False

    # --- 失敗時のプロンプトデバッグ（必要時のみ表示） ---
    dbg = summarizer.last_prompt_debug()
    if dbg:
        with st.expander("LLMデバッグ（実送信プロンプト）"):
            st.markdown(dbg)