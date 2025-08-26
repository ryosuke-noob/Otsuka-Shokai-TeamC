# app_src/components/whisper_page.py
from __future__ import annotations
import time, queue, threading
from typing import Optional, Tuple, Dict
import numpy as np
import streamlit as st
from streamlit_webrtc import webrtc_streamer, WebRtcMode

# ===== グローバル保存先：ここに逐次テキストを貯める =====
GLOBAL_TRANSCRIPTS: Dict[str, str] = {}

# ===== 固定パラメータ =====
ASR_SR    = 16000
CHUNK_SEC = 15.0
STEP_SEC  = 5.0
SAFE_TAIL = 0.5
SEMITONES = 12         # +12半音 = 2倍速
SPEED     = float(2 ** (SEMITONES / 12.0))
LANG      = "ja"
FP16      = False
DESIRED_BROWSER_SR = 48000

@st.cache_resource(show_spinner=False)
def _load_whisper():
    import whisper
    return whisper.load_model("small")

# ---- utilities (all np.float32) ----
def _mono(a: np.ndarray) -> np.ndarray:
    if a.ndim == 1: return a
    ch_axis = 0 if a.shape[0] <= a.shape[-1] else -1
    return a.mean(axis=ch_axis)

def _to_float_unit(a: np.ndarray) -> np.ndarray:
    if a.dtype == np.int16: return (a.astype(np.float32) / 32768.0)
    if a.dtype == np.int32: return (a.astype(np.float32) / 2147483648.0)
    a = a.astype(np.float32, copy=False)
    if a.size and float(np.max(np.abs(a))) > 1.5: return a / 32768.0
    return a

def _resample_linear(x: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    if not x.size or sr_from == sr_to: return x.astype(np.float32, copy=False)
    n_to = int(round(x.shape[-1] * sr_to / sr_from))
    if n_to <= 0: return np.zeros(0, dtype=np.float32)
    src = np.linspace(0, x.shape[-1] - 1, num=n_to, dtype=np.float32)
    i0 = np.floor(src).astype(np.int32); i1 = np.clip(i0+1, 0, x.shape[-1]-1)
    frac = src - i0
    y = (np.float32(1.0) - frac) * x[i0] + frac * x[i1]
    return y.astype(np.float32, copy=False)

def _time_scale_1d(x: np.ndarray, speed: float) -> np.ndarray:
    if not x.size or abs(speed-1.0) < 1e-6: return x.astype(np.float32, copy=False)
    new_len = max(1, int(round(len(x)/speed)))
    idx = np.linspace(0, len(x)-1, num=new_len, dtype=np.float32)
    i0 = np.floor(idx).astype(np.int32); i1 = np.clip(i0+1, 0, len(x)-1)
    frac = idx - i0
    y = (np.float32(1.0) - frac) * x[i0] + frac * x[i1]
    return y.astype(np.float32, copy=False)

# ===== 公開API：他タブから現在の文字列を取得したい場合に使える =====
def get_live_transcript(meeting_id: Optional[str]) -> str:
    key = str(meeting_id or "default")
    return GLOBAL_TRANSCRIPTS.get(key, "")

# ===== メインUI（タブから呼ぶ） =====
def render_whisper_page(dbsvc=None, meeting_id: Optional[str] = None):
    model = _load_whisper()
    key = str(meeting_id or "default")

    # 初期化：グローバル保存先を用意
    GLOBAL_TRANSCRIPTS.setdefault(key, "")

    # セッション内Queues（UIスレッドが作成）
    AUDIO_Q: queue.Queue[Tuple[np.ndarray, int]] = st.session_state.get(f"{key}_AUDIO_Q") or queue.Queue(maxsize=256)
    SEG_Q:   queue.Queue[str]                    = st.session_state.get(f"{key}_SEG_Q")   or queue.Queue(maxsize=64)
    HB_Q:    queue.Queue[float]                  = st.session_state.get(f"{key}_HB_Q")    or queue.Queue(maxsize=1)  # heartbeat
    st.session_state[f"{key}_AUDIO_Q"] = AUDIO_Q
    st.session_state[f"{key}_SEG_Q"]   = SEG_Q
    st.session_state[f"{key}_HB_Q"]    = HB_Q

    # --- WebRTC callback（st.*禁止） ---
    def audio_frame_callback(frame):
        a = _mono(frame.to_ndarray())
        a = _to_float_unit(a)
        if a.size:
            sr = int(getattr(frame, "sample_rate", None) or DESIRED_BROWSER_SR)
            # 音声
            try:
                AUDIO_Q.put_nowait((a.copy(), sr))
            except queue.Full:
                try: AUDIO_Q.get_nowait()
                except queue.Empty: pass
                try: AUDIO_Q.put_nowait((a.copy(), sr))
                except queue.Full: pass
            # ハートビート（最新のみ保持）
            try:
                while True: HB_Q.get_nowait()
            except queue.Empty:
                pass
            try:
                HB_Q.put_nowait(time.time())
            except queue.Full:
                pass
        return frame

    # --- 逐次ASRワーカー（15秒窓／5秒おき／重複抑制） ---
    def transcriber_worker(stop_evt: threading.Event):
        ring = np.zeros(0, dtype=np.float32)
        committed_until = 0
        next_proc_at = int(STEP_SEC * ASR_SR)
        CHUNK_S = int(CHUNK_SEC * ASR_SR); STEP_S = int(STEP_SEC * ASR_SR); SAFE_S = int(SAFE_TAIL * ASR_SR)

        while not stop_evt.is_set() or not AUDIO_Q.empty():
            # 取り込み：16k化 → 時間圧縮（2×）→ ring
            try:
                a, sr = AUDIO_Q.get(timeout=0.1)
                y16 = _resample_linear(a, sr, ASR_SR)
                y16 = _time_scale_1d(y16, SPEED)
                ring = np.concatenate([ring, y16])
            except queue.Empty:
                pass

            # 5秒ごとに末尾15秒を認識
            if len(ring) >= next_proc_at:
                start_idx = max(0, len(ring) - CHUNK_S)
                win = ring[start_idx: len(ring)]
                if win.size:
                    try:
                        res = model.transcribe(
                            win.astype(np.float32, copy=False),
                            language=(None if LANG == "auto" else LANG),
                            temperature=0.0,
                            condition_on_previous_text=False,
                            fp16=FP16,
                            verbose=False,
                        )
                        for seg in res.get("segments") or []:
                            e = start_idx + int(round(float(seg.get("end", 0.0)) * ASR_SR))
                            txt = (seg.get("text") or "").strip()
                            if txt and e <= len(ring) - SAFE_S and e > committed_until:
                                try: SEG_Q.put_nowait(txt)
                                except queue.Full: pass
                                committed_until = e
                    except Exception:
                        pass
                next_proc_at += STEP_S

        # tail確定
        start_idx = max(0, len(ring) - CHUNK_S)
        win = ring[start_idx: len(ring)]
        if win.size:
            try:
                res = model.transcribe(
                    win.astype(np.float32, copy=False),
                    language=(None if LANG == "auto" else LANG),
                    temperature=0.0,
                    condition_on_previous_text=False,
                    fp16=FP16,
                    verbose=False,
                )
                for seg in res.get("segments") or []:
                    e = start_idx + int(round(float(seg.get("end", 0.0)) * ASR_SR))
                    txt = (seg.get("text") or "").strip()
                    if txt and e > committed_until:
                        try: SEG_Q.put_nowait(txt)
                        except queue.Full: pass
                        committed_until = e
            except Exception:
                pass

    # --- WebRTC起動（SENDONLY） ---
    ctx = webrtc_streamer(
        key=f"{key}_rtc",
        mode=WebRtcMode.SENDONLY,
        media_stream_constraints={"audio": {"channelCount": 1, "sampleRate": DESIRED_BROWSER_SR,
                                            "echoCancellation": False, "noiseSuppression": False,
                                            "autoGainControl": False},
                                  "video": False},
        audio_frame_callback=audio_frame_callback,
        async_processing=True,
    )

    # --- Transcript 表示（placeholder をループ更新：アプリ全体は再実行しない） ---
    st.subheader("Transcript（このタブだけ更新）")
    ph = st.empty()  # ここだけ上書き描画する
    ph.text_area("Transcript", value=GLOBAL_TRANSCRIPTS[key], height=280)

    # Start / Stop に合わせてワーカ起動停止
    if "running" not in st.session_state: st.session_state["running"] = {}
    running = st.session_state["running"].get(key, False)

    # Start 検知
    if bool(ctx and ctx.state.playing) and not running:
        # 既存テキストは保持（必要なら消す→ GLOBAL_TRANSCRIPTS[key] = ""）
        stop_evt = threading.Event()
        st.session_state[f"{key}_stop_evt"] = stop_evt
        threading.Thread(target=transcriber_worker, args=(stop_evt,), daemon=True).start()
        st.session_state["running"][key] = True

    last_hb = time.time()
    try:
        last_hb = HB_Q.get_nowait()
    except queue.Empty:
        pass

    # 0.5秒刻みでSEGを消費して描画。※この while はこのタブ内だけを更新します
    while bool(ctx and ctx.state.playing):
        # SEG を吸い上げてグローバルに反映
        new_any = False
        while True:
            try:
                seg = SEG_Q.get_nowait()
                if seg:
                    GLOBAL_TRANSCRIPTS[key] += (seg + "\n")
                    new_any = True
            except queue.Empty:
                break
        if new_any:
            ph.text_area("Transcript", value=GLOBAL_TRANSCRIPTS[key], height=280)

        try:
            last_hb = HB_Q.get_nowait()
        except queue.Empty:
            pass
        if time.time() - last_hb > 2.0:
            break

        time.sleep(0.5)

    if st.session_state["running"].get(key, False) and not bool(ctx and ctx.state.playing):
        if st.session_state.get(f"{key}_stop_evt"):
            st.session_state[f"{key}_stop_evt"].set()
        st.session_state["running"][key] = False

    drained = False
    while True:
        try:
            seg = SEG_Q.get_nowait()
            if seg:
                GLOBAL_TRANSCRIPTS[key] += (seg + "\n")
                drained = True
        except queue.Empty:
            break
    if drained:
        ph.text_area("Transcript", value=GLOBAL_TRANSCRIPTS[key], height=280)
