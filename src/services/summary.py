# # core/summary_service.py
# from __future__ import annotations
# import time, json, re, hashlib, threading, queue
# from typing import Dict, List, Literal, Callable
# from pydantic import BaseModel, Field
# import streamlit as st
# import os

# AZURE_API_VERSION  = "2025-03-01-preview"
# AZURE_CHAT_MODEL   = "gpt-5-mini"

# # --- Pydantic schema ---
# class LineOpModel(BaseModel):
#     op: Literal["add_after","add_end","update","delete"]
#     line_no: int | None = None
#     text: str | None = None

# class LinePatchV1Model(BaseModel):
#     ops: List[LineOpModel] = Field(default_factory=list)
#     phase: Literal["現状・課題・ニーズ把握","商品要件把握","契約条件把握"]

# @st.cache_resource(show_spinner=False)
# def load_llm_client():
#     from openai import AzureOpenAI
#     endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
#     api_key  = os.getenv("AZURE_OPENAI_API_KEY")
#     if not endpoint or not api_key:
#         st.warning("Azure OpenAI の環境変数(AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY)が未設定です。")
#     client = AzureOpenAI(api_version=AZURE_API_VERSION,
#                          azure_endpoint=endpoint,
#                          api_key=api_key)
#     return client, AZURE_CHAT_MODEL

# # --- helpers (必要分だけ移植) ---
# def _norm_text(s: str) -> str:
#     import re
#     return re.sub(r"\s+"," ",(s or "")).strip()

# _LEADING_BULLET_RE = re.compile(r"^\s*(?:[-*・•]|[0-9０-９]+[.)．])\s+")
# def _strip_leading_bullet(s: str) -> str:
#     return _LEADING_BULLET_RE.sub("", (s or "")).strip()

# def _gen_id(prefix: str, text: str) -> str:
#     base = _norm_text(text) or "line"
#     h = hashlib.sha1(base.encode("utf-8")).hexdigest()[:8]
#     return f"{prefix}_{h}"

# def _apply_line_patch(state: Dict, patch: Dict):
#     if not patch: return
#     items: List[Dict] = state.get("lines", [])
#     for op in patch.get("ops", []):
#         action = op.get("op"); line_no = int(op.get("line_no") or 0)
#         text = _strip_leading_bullet(_norm_text(op.get("text","")))
#         if action == "add_after":
#             if not text: continue
#             new_item = {"id": _gen_id("L", text), "text": text}
#             if line_no <= 0: items.insert(0, new_item)
#             elif 1 <= line_no <= len(items): items.insert(line_no, new_item)
#             else: items.append(new_item)
#         elif action == "add_end":
#             if not text: continue
#             items.append({"id": _gen_id("L", text), "text": text})
#         elif action == "update":
#             if 1 <= line_no <= len(items) and text:
#                 items[line_no-1]["text"] = text
#         elif action == "delete":
#             if 1 <= line_no <= len(items): del items[line_no-1]
#     state["lines"] = items

#     state["phase"] = patch.get("phase","")

# def _dedupe_lines(state: Dict):
#     seen, out = set(), []
#     for it in state.get("lines", []):
#         t = (it.get("text") or "").strip()
#         if not t or t in seen: continue
#         seen.add(t); out.append(it)
#     state["lines"] = out

# def _render_markdown(state: Dict) -> str:
#     lines = state.get("lines", [])
#     if not lines: return "（要約を生成中…）"
#     md = []
#     for i, it in enumerate(lines, start=1):
#         t = _strip_leading_bullet(it.get("text",""))
#         if t: md.append(f"{i}. {t}")
#     return "\n".join(md)

# def _lines_tail_text(state: Dict, n: int) -> str:
#     lines = state.get("lines", [])
#     start = max(0, len(lines)-n)
#     chunks=[]
#     for i in range(start, len(lines)):
#         t = _strip_leading_bullet(lines[i].get("text",""))
#         if t: chunks.append(f"{i+1}. {t}")
#     return "\n".join(chunks)

# def _extract_json_block(s: str) -> dict:
#     if not s: return {}
#     try: return json.loads(s)
#     except Exception: pass
#     m = re.search(r"```json\s*(\{.*?\})\s*```", s, flags=re.DOTALL)
#     if m:
#         try: return json.loads(m.group(1))
#         except Exception: pass
#     m = re.search(r"(\{.*\})", s, flags=re.DOTALL)
#     if m:
#         try: return json.loads(m.group(1))
#         except Exception: pass
#     return {}

# def _clean_asr_text(raw: str, max_chars=2800) -> str:
#     FILLERS = {"あの","あのー","えっと","えっ","えー","うーん","その","ええと","まぁ","そうですね","はい","ありがとうございます","なるほど"}
#     if not raw: return ""
#     lines = [re.sub(r"\s+"," ", ln.strip()) for ln in raw.splitlines()]
#     out, prev = [], ""
#     for ln in lines:
#         if not ln or ln in FILLERS or len(ln)<=1 or ln==prev: continue
#         out.append(ln); prev = ln
#     s = "。".join(out)
#     s = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[redacted-email]", s)
#     s = re.sub(r"\b(?:\+?\d{1,3}[-\s]?)?(?:\d{2,4}[-\s]?){2,3}\d{3,4}\b", "[redacted-phone]", s)
#     s = re.sub(r"\b[A-Za-z0-9/_-]{24,}\b", "[redacted-token]", s)
#     return s[:max_chars]

# class SummaryService:
#     def __init__(self, *, client, model_name: str,
#                  overlap_chars=900, tail_lines_for_llm=24):
#         self.client = client
#         self.model_name = model_name
#         self.OVERLAP = overlap_chars
#         self.TAIL = tail_lines_for_llm
#         self.state: Dict = {"lines": []}
#         self.summary_md = "（要約を生成中…）"
#         self._last_idx = 0
#         self._last_debug_md: str | None = None
#         self._stop_evt = threading.Event()
#         self._th = None

#     def start(self, *, transcript_getter: Callable[[], str], tick_q: queue.Queue):
#         self._getter = transcript_getter
#         self._tick_q = tick_q
#         if self._th and self._th.is_alive(): return
#         self._stop_evt.clear()
#         self._th = threading.Thread(target=self._worker, daemon=True)
#         self._th.start()

#     def stop(self):
#         self._stop_evt.set()

#     def summary_markdown(self) -> str:
#         return self.summary_md

#     def shodan_phase(self) -> str:
#         return self.state.get("phase","")

#     def last_prompt_debug(self) -> str | None:
#         return self._last_debug_md

#     def _worker(self):
#         while not self._stop_evt.is_set():
#             try:
#                 self._tick_q.get(timeout=1.0)
#             except queue.Empty:
#                 continue

#             full_txt = self._getter() or ""
#             if len(full_txt) <= self._last_idx:
#                 continue

#             start = max(0, self._last_idx - self.OVERLAP)
#             end   = len(full_txt)
#             context = _clean_asr_text(full_txt[start:end])
#             tail_text = _lines_tail_text(self.state, self.TAIL)
#             total = len(self.state.get("lines", []))

#             system = (
#                 "あなたは文字起こしテキスト要約アシスタントです。"
#             )
#             schema = '{"ops":[{"op":"add_after","line_no":<int>,"text":"..."},{"op":"add_end","text":"..."},{"op":"update","line_no":<int>,"text":"..."},{"op":"delete","line_no":<int>}]}'
#             user = (
#                 "営業担当者向けの『会話フロー要約』を、時系列の箇条書きで更新してください。"
#                 "人称代名詞は「先方」「こちら」を用います。"
#                 "挨拶や相づち等のノイズは無視し、確実な事実・合意・依頼・疑問・次アクションのみ残してください。"
#                 "また、現在の商談の状況を「現状・課題・ニーズ把握」、「商品要件把握」、「契約条件把握」から選択してください。"
#                 "あくまで営業担当者用の要約であるため、基本は相手の発話に元づく内容をまとめてください\n\n"
#                 "既存要約（末尾。行番号は全体の通し番号）:\n"
#                 f"{tail_text or '(なし)'}\n\n"
#                 f"総行数: {total}\n"
#                 "文脈＋差分（ASR生テキスト。末尾が新しい文字起こし）:\n"
#                 f"{context}\n\n"
#                 "ルール: 追加は add_after または add_end、既存要約の修正は update、不要は delete。"
#                 "変更が不要または確信が持てない場合は ops は空配列。"
#                 "営業と先方の発言をまとめて事実として文語体で記述。「～と述べた」ではなく「～」と記述。"
#                 "商談の状況は必ず1つ選択し、phaseに設定する。"
#             )

#             patch = {}
#             try:
#                 resp = self.client.responses.parse(
#                     model=self.model_name,
#                     instructions=system,
#                     input=[{"role":"user","content":[{"type":"input_text","text":user}]}],
#                     text_format=LinePatchV1Model,
#                     max_output_tokens=600,
#                     reasoning={"effort":"low"},
#                 )
#                 parsed = getattr(resp, "output_parsed", None)
#                 if parsed: patch = parsed.model_dump()
#             except Exception as e:
#                 self._last_debug_md = self._debug_md(system, user, e)
#                 try:
#                     fb = self.client.chat.completions.create(
#                         model=self.model_name,
#                         messages=[{"role":"system","content":system},{"role":"user","content":user}],
#                         max_completion_tokens=600,
#                     )
#                     patch = _extract_json_block(fb.choices[0].message.content if fb and fb.choices else "")
#                 except Exception as ee:
#                     self._last_debug_md = self._debug_md(system, user, ee)
#                     self._last_idx = max(0, len(full_txt)-self.OVERLAP)
#                     continue

#             if patch and isinstance(patch.get("ops", None), list) and isinstance(patch.get("phase",""), str):
#                 _apply_line_patch(self.state, patch)
#                 _dedupe_lines(self.state)
#                 self.summary_md = _render_markdown(self.state)
#                 rewind = min(self.OVERLAP//2, len(full_txt))
#                 self._last_idx = max(0, end - rewind)


#     @staticmethod
#     def _debug_md(instructions: str, user: str, err: Exception) -> str:
#         def _trim(s: str, n=4000): return s if len(s)<=n else s[:n]+"\n…(truncated)"
#         return (f"（要約エラー: {err}）\n\n"
#                 "**instructions**\n```text\n"+_trim(instructions)+"\n```\n\n"
#                 "**user**\n```text\n"+_trim(user)+"\n```")

# core/summary_service.py
from __future__ import annotations
import time, json, re, hashlib, threading, queue
from typing import Dict, List, Literal, Callable
from pydantic import BaseModel, Field
import streamlit as st
import os

AZURE_API_VERSION  = "2025-03-01-preview"
AZURE_CHAT_MODEL   = "gpt-5-mini"

# --- Pydantic schema ---
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
                 overlap_chars=900, tail_lines_for_llm=24):
        self.client = client
        self.model_name = model_name
        self.OVERLAP = overlap_chars
        self.TAIL = tail_lines_for_llm
        self.state: Dict = {"lines": []}
        # self.summary_md = "（要約を生成中…）"
        self.summary_md = ""
        self._last_idx = 0
        self._last_debug_md: str | None = None
        self._stop_evt = threading.Event()
        self._th = None

    def start(self, *, transcript_getter: Callable[[], str], tick_q: queue.Queue):
        self._getter = transcript_getter
        self._tick_q = tick_q
        if self._th and self._th.is_alive(): return
        self._stop_evt.clear()
        self._th = threading.Thread(target=self._worker, daemon=True)
        self._th.start()

    def stop(self):
        self._stop_evt.set()

    def summary_markdown(self) -> str:
        return self.summary_md

    def shodan_phase(self) -> str:
        return self.state.get("phase","")

    def last_prompt_debug(self) -> str | None:
        return self._last_debug_md

    def _worker(self):
        while not self._stop_evt.is_set():
            # 1) 最初の tick を待つ（来なければ 1 秒でループ）
            try:
                self._tick_q.get(timeout=1.0)
            except queue.Empty:
                continue

            # 2) ここで「たまっている tick を全部捨てる（= 最新だけにする）」
            drained = 1
            while True:
                try:
                    self._tick_q.get_nowait()
                    drained += 1
                except queue.Empty:
                    break
            # ↑ drained は統計用。必要なければ未使用でOK

            # 3) いま時点の全文スナップショットで“1回だけ”要約を回す
            full_txt = self._getter() or ""
            if len(full_txt) <= self._last_idx:
                # 新規テキストが無ければスキップ
                continue

            start = max(0, self._last_idx - self.OVERLAP)
            end   = len(full_txt)
            context = _clean_asr_text(full_txt[start:end])
            tail_text = _lines_tail_text(self.state, self.TAIL)
            total = len(self.state.get("lines", []))

            system = ("あなたは文字起こしテキスト要約アシスタントです。")
            user = (
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

            patch = {}
            try:
                resp = self.client.responses.parse(
                    model=self.model_name,
                    instructions=system,
                    input=[{"role":"user","content":[{"type":"input_text","text":user}]}],
                    text_format=LinePatchV1Model,
                    max_output_tokens=600,
                    reasoning={"effort":"low"},
                )
                parsed = getattr(resp, "output_parsed", None)
                if parsed:
                    patch = parsed.model_dump()
            except Exception as e:
                self._last_debug_md = self._debug_md(system, user, e)
                try:
                    fb = self.client.chat.completions.create(
                        model=self.model_name,
                        messages=[{"role":"system","content":system},{"role":"user","content":user}],
                        max_completion_tokens=600,
                    )
                    patch = _extract_json_block(fb.choices[0].message.content if fb and fb.choices else "")
                except Exception as ee:
                    self._last_debug_md = self._debug_md(system, user, ee)
                    self._last_idx = max(0, len(full_txt) - self.OVERLAP)
                    continue

            if patch and isinstance(patch.get("ops", None), list) and isinstance(patch.get("phase",""), str):
                _apply_line_patch(self.state, patch)
                _dedupe_lines(self.state)
                self.summary_md = _render_markdown(self.state)

                # 次回のために処理位置を前進（少し巻き戻しもする）
                rewind = min(self.OVERLAP // 2, len(full_txt))
                self._last_idx = max(0, end - rewind)



    @staticmethod
    def _debug_md(instructions: str, user: str, err: Exception) -> str:
        def _trim(s: str, n=4000): return s if len(s)<=n else s[:n]+"\n…(truncated)"
        return (f"（要約エラー: {err}）\n\n"
                "**instructions**\n```text\n"+_trim(instructions)+"\n```\n\n"
                "**user**\n```text\n"+_trim(user)+"\n```")