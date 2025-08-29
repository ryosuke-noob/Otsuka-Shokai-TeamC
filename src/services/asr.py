from __future__ import annotations
import time, queue, threading
import numpy as np
import streamlit as st

DESIRED_BROWSER_SR = 48000

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

@st.cache_resource(show_spinner=False)
def load_whisper():
    import whisper
    return whisper.load_model("turbo")   # 既定は turbo

from typing import Callable, Optional, List

class ASRService:
    def __init__(self, *, whisper_model,
                 asr_sr=16000, chunk_sec=30.0, step_sec=10.0, safe_tail=0.5,
                 speed=2.0, lang="ja", fp16=False, desired_browser_sr=48000,
                 segment_sink: Optional[Callable[[List[str]], None]] = None,):
        self.model = whisper_model
        self.ASR_SR = asr_sr
        self.CHUNK_S = int(chunk_sec * asr_sr)
        self.STEP_S  = int(step_sec  * asr_sr)
        self.SAFE_S  = int(safe_tail * asr_sr)
        self.SPEED   = speed
        self.LANG    = lang
        self.FP16    = fp16
        self.DESIRED_BROWSER_SR = desired_browser_sr

        self.audio_q: queue.Queue[tuple[np.ndarray,int]] = queue.Queue(maxsize=256)
        self.seg_q:   queue.Queue[str] = queue.Queue(maxsize=128)
        self.hb_q:    queue.Queue[float] = queue.Queue(maxsize=1)
        self.tick_q:  queue.Queue[int] = queue.Queue(maxsize=64)

        self._stop_evt = threading.Event()
        self._th = None

        self._segment_sink = segment_sink

    def set_segment_sink(self, sink: Optional[Callable[[List[str]], None]]):
        self._segment_sink = sink

    # ---- light utils（ASRサービス内に局所化） ----
    @staticmethod
    def _mono(a: np.ndarray) -> np.ndarray:
        if a.ndim == 1: return a
        ch_axis = 0 if a.shape[0] <= a.shape[-1] else -1
        return a.mean(axis=ch_axis)

    @staticmethod
    def _to_float(a: np.ndarray) -> np.ndarray:
        import numpy as np
        if a.dtype == np.int16: return (a.astype(np.float32) / 32768.0)
        if a.dtype == np.int32: return (a.astype(np.float32) / 2147483648.0)
        a = a.astype(np.float32, copy=False)
        if a.size and float(np.max(np.abs(a))) > 1.5: return a / 32768.0
        return a

    @staticmethod
    def _resample_linear(x, sr_from, sr_to):
        import numpy as np
        if not x.size or sr_from == sr_to: return x.astype(np.float32, copy=False)
        n_to = int(round(x.shape[-1] * sr_to / sr_from))
        if n_to <= 0: return np.zeros(0, dtype=np.float32)
        src = np.linspace(0, x.shape[-1]-1, num=n_to, dtype=np.float32)
        i0 = np.floor(src).astype(np.int32); i1 = np.clip(i0+1, 0, x.shape[-1]-1)
        frac = src - i0
        y = (np.float32(1.0)-frac)*x[i0] + frac*x[i1]
        return y.astype(np.float32, copy=False)

    @staticmethod
    def _time_scale_1d(x, speed):
        import numpy as np
        if not x.size or abs(speed-1.0) < 1e-6: return x.astype(np.float32, copy=False)
        new_len = max(1, int(round(len(x)/speed)))
        idx = np.linspace(0, len(x)-1, num=new_len, dtype=np.float32)
        i0 = np.floor(idx).astype(np.int32); i1 = np.clip(i0+1, 0, len(x)-1)
        frac = idx - i0
        y = (np.float32(1.0)-frac)*x[i0] + frac*x[i1]
        return y.astype(np.float32, copy=False)

    def audio_frame_callback(self, frame):
        a = self._mono(frame.to_ndarray())
        a = self._to_float(a)
        if a.size:
            sr = int(getattr(frame, "sample_rate", None) or self.DESIRED_BROWSER_SR)
            try:
                self.audio_q.put_nowait((a.copy(), sr))
            except queue.Full:
                try: self.audio_q.get_nowait()
                except queue.Empty: pass
                try: self.audio_q.put_nowait((a.copy(), sr))
                except queue.Full: pass
            try:
                while True: self.hb_q.get_nowait()
            except queue.Empty:
                pass
            try: self.hb_q.put_nowait(time.time())
            except queue.Full: pass
        return frame

    def _transcribe_step(self, win: np.ndarray):
        return self.model.transcribe(
            win.astype(np.float32, copy=False),
            language=(None if self.LANG == "auto" else self.LANG),
            temperature=0.0,
            condition_on_previous_text=False,
            fp16=self.FP16,
            verbose=False,
        )

    def _worker(self):
        import numpy as np
        ring = np.zeros(0, dtype=np.float32)
        committed_until = 0
        next_proc_at = self.STEP_S

        while not self._stop_evt.is_set() or not self.audio_q.empty():
            try:
                a, sr = self.audio_q.get(timeout=0.1)
                y16 = self._resample_linear(a, sr, self.ASR_SR)
                y16 = self._time_scale_1d(y16, self.SPEED)
                ring = np.concatenate([ring, y16])
            except queue.Empty:
                pass

            if len(ring) >= next_proc_at:
                start_idx = max(0, len(ring) - self.CHUNK_S)
                win = ring[start_idx: len(ring)]
                committed = False
                step_lines: List[str] = []
                if win.size:
                    try:
                        res = self._transcribe_step(win)
                        for seg in res.get("segments") or []:
                            e = start_idx + int(round(float(seg.get("end",0.0))*self.ASR_SR))
                            txt = (seg.get("text") or "").strip()
                            if txt and e <= len(ring) - self.SAFE_S and e > committed_until:
                                try: self.seg_q.put_nowait(txt)
                                except queue.Full: pass
                                committed_until = e
                                step_lines.append(txt)
                                committed = True
                    except Exception:
                        pass
                if committed:
                    # 先に sink へ流し、その後 tick 通知
                    if self._segment_sink and step_lines:
                        try: self._segment_sink(step_lines)
                        except Exception: pass
                    try: self.tick_q.put_nowait(1)
                    except queue.Full: pass
                next_proc_at += self.STEP_S

        # tail
        start_idx = max(0, len(ring) - self.CHUNK_S)
        win = ring[start_idx: len(ring)]
        if win.size:
            try:
                res = self._transcribe_step(win)
                committed = False
                tail_lines: List[str] = []
                for seg in res.get("segments") or []:
                    e = start_idx + int(round(float(seg.get("end",0.0))*self.ASR_SR))
                    txt = (seg.get("text") or "").strip()
                    if txt and e > committed_until:
                        try: self.seg_q.put_nowait(txt)
                        except queue.Full: pass
                        committed_until = e
                        committed = True
                        tail_lines.append(txt)
                if committed:
                    if self._segment_sink and tail_lines:
                        try: self._segment_sink(tail_lines)
                        except Exception: pass
                    try: self.tick_q.put_nowait(1)
                    except queue.Full: pass
            except Exception:
                pass

    def start(self):
        if self._th and self._th.is_alive(): return
        self._stop_evt.clear()
        self._th = threading.Thread(target=self._worker, daemon=True)
        self._th.start()

    def stop(self):
        self._stop_evt.set()
        if self._th and self._th.is_alive():
            self._th.join(timeout=1.0)

    def drain_segments(self) -> list[str]:
        out = []
        while True:
            try: out.append(self.seg_q.get_nowait())
            except queue.Empty: break
        return out
