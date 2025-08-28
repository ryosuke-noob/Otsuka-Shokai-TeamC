from __future__ import annotations
import time, json, re, hashlib, threading, queue
from typing import Dict, List, Literal, Callable
from pydantic import BaseModel, Field
import streamlit as st
import os

AZURE_API_VERSION  = "2025-03-01-preview"
AZURE_CHAT_MODEL   = "gpt-5-mini"

class LineOpModel(BaseModel):
    op: Literal["add_after","add_end","update","delete"]
    line_no: int | None = None
    text: str | None = None

class LinePatchV1Model(BaseModel):
    ops: List[LineOpModel] = Field(default_factory=list)
    phase: Literal["現状・課題・ニーズ把握","商品要件把握","契約条件把握"]

@st.cache_resource(show_spinner=False)
def load_llm_client():
    from openai import AzureOpenAI
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key  = os.getenv("AZURE_OPENAI_API_KEY")
    if not endpoint or not api_key:
        st.warning("Azure OpenAI の環境変数(AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY)が未設定です。")
    client = AzureOpenAI(api_version=AZURE_API_VERSION,
                         azure_endpoint=endpoint,
                         api_key=api_key)
    return client, AZURE_CHAT_MODEL

# --- helpers (必要分だけ移植) ---
def _norm_text(s: str) -> str:
    import re
    return re.sub(r"\s+"," ",(s or "")).strip()

_LEADING_BULLET_RE = re.compile(r"^\s*(?:[-*・•]|[0-9０-９]+[.)．])\s+")
def _strip_leading_bullet(s: str) -> str:
    return _LEADING_BULLET_RE.sub("", (s or "")).strip()

def _gen_id(prefix: str, text: str) -> str:
    base = _norm_text(text) or "line"
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}_{h}"

def _apply_line_patch(state: Dict, patch: Dict):
    if not patch: return
    items: List[Dict] = state.get("lines", [])
    for op in patch.get("ops", []):
        action = op.get("op"); line_no = int(op.get("line_no") or 0)
        text = _strip_leading_bullet(_norm_text(op.get("text","")))
        if action == "add_after":
            if not text: continue
            new_item = {"id": _gen_id("L", text), "text": text}
            if line_no <= 0: items.insert(0, new_item)
            elif 1 <= line_no <= len(items): items.insert(line_no, new_item)
            else: items.append(new_item)
        elif action == "add_end":
            if not text: continue
            items.append({"id": _gen_id("L", text), "text": text})
        elif action == "update":
            if 1 <= line_no <= len(items) and text:
                items[line_no-1]["text"] = text
        elif action == "delete":
            if 1 <= line_no <= len(items): del items[line_no-1]
    state["lines"] = items

    state["phase"] = patch.get("phase","")

def _dedupe_lines(state: Dict):
    seen, out = set(), []
    for it in state.get("lines", []):
        t = (it.get("text") or "").strip()
        if not t or t in seen: continue
        seen.add(t); out.append(it)
    state["lines"] = out

def _render_markdown(state: Dict) -> str:
    lines = state.get("lines", [])
    if not lines: return "（要約を生成中…）"
    md = []
    for i, it in enumerate(lines, start=1):
        t = _strip_leading_bullet(it.get("text",""))
        if t: md.append(f"{i}. {t}")
    return "\n".join(md)

def _lines_tail_text(state: Dict, n: int) -> str:
    lines = state.get("lines", [])
    start = max(0, len(lines)-n)
    chunks=[]
    for i in range(start, len(lines)):
        t = _strip_leading_bullet(lines[i].get("text",""))
        if t: chunks.append(f"{i+1}. {t}")
    return "\n".join(chunks)

def _extract_json_block(s: str) -> dict:
    if not s: return {}
    try: return json.loads(s)
    except Exception: pass
    m = re.search(r"```json\s*(\{.*?\})\s*```", s, flags=re.DOTALL)
    if m:
        try: return json.loads(m.group(1))
        except Exception: pass
    m = re.search(r"(\{.*\})", s, flags=re.DOTALL)
    if m:
        try: return json.loads(m.group(1))
        except Exception: pass
    return {}

def _clean_asr_text(raw: str, max_chars=2800) -> str:
    FILLERS = {"あの","あのー","えっと","えっ","えー","うーん","その","ええと","まぁ","そうですね","はい","ありがとうございます","なるほど"}
    if not raw: return ""
    lines = [re.sub(r"\s+"," ", ln.strip()) for ln in raw.splitlines()]
    out, prev = [], ""
    for ln in lines:
        if not ln or ln in FILLERS or len(ln)<=1 or ln==prev: continue
        out.append(ln); prev = ln
    s = "。".join(out)
    s = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[redacted-email]", s)
    s = re.sub(r"\b(?:\+?\d{1,3}[-\s]?)?(?:\d{2,4}[-\s]?){2,3}\d{3,4}\b", "[redacted-phone]", s)
    s = re.sub(r"\b[A-Za-z0-9/_-]{24,}\b", "[redacted-token]", s)
    return s[:max_chars]
class SummaryService:
    def __init__(self, *, client, model_name: str,
                 overlap_chars=900, tail_lines_for_llm=24,
                 dispatch_interval_sec=12, coalesce_idle_sec=3,
                 max_inflight=2):
        self.client = client
        self.model_name = model_name
        self.OVERLAP = overlap_chars
        self.TAIL = tail_lines_for_llm

        self.state: Dict = {"lines": []}
        self.summary_md = ""
        self._last_idx = 0

        # --- 新規: ディスパッチ制御 ---
        self._dispatch_interval_sec = dispatch_interval_sec  # 10-20秒くらいに調整
        self._coalesce_idle_sec = coalesce_idle_sec
        self._last_sent_at = 0.0
        self._dirty = False
        self._last_seen_len = 0
        self._last_change_at = 0.0

        # --- 並列・世代管理 ---
        self._max_inflight = max_inflight
        self._inflight: Dict[int, Dict] = {}  # req_id -> meta
        self._req_seq = 0
        self._latest_applied_req = 0
        self._lock = threading.Lock()

        # --- 障害対応 ---
        self._err_count = 0
        self._cb_open_until = 0.0          # circuit breaker open-until(unixtime)
        self._cb_fail_threshold = 5         # 連続失敗で開く
        self._cb_open_seconds = 45          # 開いてる時間

        self._last_debug_md: str | None = None
        self._stop_evt = threading.Event()
        self._th = None

    # 任意: 外部から軽く起床
    def nudge(self):
        try:
            self._tick_q.put_nowait(1)
        except Exception:
            pass

    def stop(self): self._stop_evt.set()
    def summary_markdown(self) -> str: return self.summary_md
    def shodan_phase(self) -> str: return self.state.get("phase","")
    def last_prompt_debug(self) -> str | None: return self._last_debug_md

    def start(self, *, transcript_getter: Callable[[], str], tick_q: queue.Queue):
        self._getter = transcript_getter
        self._tick_q = tick_q
        if self._th and self._th.is_alive(): return
        self._stop_evt.clear()
        self._th = threading.Thread(target=self._worker, daemon=True)
        self._th.start()

    # -------- LLM呼び出し（リトライ＋フォールバック） --------
    def _call_llm_for_patch(self, system: str, user: str) -> dict:
        patch = {}
        for attempt in range(3):
            try:
                if attempt < 2:
                    resp = self.client.responses.parse(
                        model=self.model_name,
                        instructions=system,
                        input=[{"role":"user","content":[{"type":"input_text","text":user}]}],
                        text_format=LinePatchV1Model,
                        max_output_tokens=600,
                        reasoning={"effort":"low"},
                    )
                    parsed = getattr(resp, "output_parsed", None)
                    if parsed: patch = parsed.model_dump()
                else:
                    fb = self.client.chat.completions.create(
                        model=self.model_name,
                        messages=[{"role":"system","content":system},{"role":"user","content":user}],
                        max_completion_tokens=600,
                    )
                    patch = _extract_json_block(fb.choices[0].message.content if fb and fb.choices else "")
                if isinstance(patch, dict):
                    return patch  # 成功
            except Exception as e:
                self._last_debug_md = self._debug_md(system, user, e)
                self._err_count += 1
                time.sleep(min(2 ** self._err_count, 10))
                continue
        return {}  # 全滅

    # -------- 応答適用（stale drop & 排他） --------
    def _apply_if_current(self, req_id: int, patch: dict, end_used: int, full_len_at_req: int):
        with self._lock:
            # 古い応答は破棄
            if req_id < self._latest_applied_req:
                self._inflight.pop(req_id, None)
                return

            # 読み取り位置は常に前進（固着回避）
            rewind = min(self.OVERLAP // 2, full_len_at_req)
            self._last_idx = max(self._last_idx, end_used - rewind)

            if isinstance(patch.get("ops", None), list) and isinstance(patch.get("phase",""), str):
                _apply_line_patch(self.state, patch)
                _dedupe_lines(self.state)
                self.summary_md = _render_markdown(self.state)
                self._latest_applied_req = req_id
                self._err_count = 0  # 成功でリセット

            self._inflight.pop(req_id, None)

    # -------- 非同期推論タスク --------
    def _infer_task(self, req_id: int, start: int, end: int, system: str, user: str, full_len_at_req: int):
        try:
            patch = self._call_llm_for_patch(system, user)
            self._apply_if_current(req_id, patch, end, full_len_at_req)
        except Exception as e:
            # ここに来るのは稀（上で捕捉済みだが保険）
            self._last_debug_md = self._debug_md(system, user, e)
            self._err_count += 1
        finally:
            # 連続失敗でサーキットを開く
            if self._err_count >= self._cb_fail_threshold:
                self._cb_open_until = time.time() + self._cb_open_seconds

    # -------- ディスパッチ兼監視ワーカー --------
    def _worker(self):
        while not self._stop_evt.is_set():
            # tickは使っても使わなくてもOK（ここでは軽く消費）
            try:
                self._tick_q.get(timeout=0.5)
                while True:
                    self._tick_q.get_nowait()
            except queue.Empty:
                pass

            now = time.time()

            # サーキットオープン中は送らない
            if now < self._cb_open_until:
                time.sleep(0.2); continue

            full_txt = self._getter() or ""
            cur_len = len(full_txt)

            # 増分検出
            if cur_len > self._last_seen_len:
                self._last_seen_len = cur_len
                self._last_change_at = now
                self._dirty = True

            # 送る条件:
            # - dirty
            # - 最後の送信から dispatch_interval_sec 経過
            # - 最終増加から coalesce_idle_sec 経過（落ち着くまで待つ）
            # - インフライトが上限未満
            can_send = (self._dirty and
                        (now - self._last_sent_at) >= self._dispatch_interval_sec and
                        (now - self._last_change_at) >= self._coalesce_idle_sec and
                        (len(self._inflight) < self._max_inflight))

            if not can_send:
                continue

            # 入力スナップショット作成（差分+テール）
            start = max(0, self._last_idx - self.OVERLAP)
            end   = cur_len
            context = _clean_asr_text(full_txt[start:end])
            tail_text = _lines_tail_text(self.state, self.TAIL)
            total = len(self.state.get("lines", []))

            req_id = self._req_seq = self._req_seq + 1
            self._inflight[req_id] = {"start": start, "end": end, "len": cur_len}
            self._last_sent_at = now
            # 連投時も最低限のアイドル待ち後にまた送れるよう dirty は残す
            # （適用時に dirty の扱いは状況次第で更新してOK）

            system = ("あなたは文字起こしテキスト要約アシスタントです。")
            user = (
                f"(meta) req_id={req_id}, txt_len={cur_len}, start={start}, end={end}\n\n"
                "営業担当者向けの『会話フロー要約』を、時系列の箇条書きで更新してください。"
                "人称代名詞は「先方」「こちら」を用います。"
                "挨拶や相づち等のノイズは無視し、確実な事実・合意・依頼・疑問・次アクションのみ残してください。"
                "また、現在の商談の状況を「現状・課題・ニーズ把握」、「商品要件把握」、「契約条件把握」から選択してください。"
                "あくまで営業担当者用の要約であるため、基本は相手の発話に元づく内容をまとめてください\n\n"
                "既存要約（末尾。行番号は全体の通し番号）:\n"
                f"{tail_text or '(なし)'}\n\n"
                f"総行数: {total}\n"
                "文脈＋差分（ASR生テキスト。末尾が新しい文字起こし）:\n"
                f"{context}\n\n"
                "ルール: 追加は add_after または add_end、既存要約の修正は update、不要は delete。"
                "変更が不要または確信が持てない場合は ops は空配列。"
                "営業と先方の発言をまとめて事実として文語体で記述。「～と述べた」ではなく「～」と記述。"
                "商談の状況は必ず1つ選択し、phaseに設定する。"
            )

            # 非同期で発射（古い応答は適用時に弾く）
            threading.Thread(
                target=self._infer_task,
                args=(req_id, start, end, system, user, cur_len),
                daemon=True
            ).start()

            # コアレス: 直後に transcript がさらに伸びても、coalesce_idle_sec 経過まで待ってから次を送る
            # （ここではループ継続で監視し続ける／sleepは不要）
            continue

    @staticmethod
    def _debug_md(instructions: str, user: str, err: Exception) -> str:
        def _trim(s: str, n=4000): return s if len(s)<=n else s[:n]+"\n…(truncated)"
        return (f"（要約エラー: {err}）\n\n"
                "**instructions**\n```text\n"+_trim(instructions)+"\n```\n\n"
                "**user**\n```text\n"+_trim(user)+"\n```")