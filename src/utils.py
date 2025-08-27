# utils.py
from __future__ import annotations
from typing import List, Dict, Any
import streamlit as st
from contextlib import contextmanager

# ==============================
# 日本語/英語ステータス
# ==============================
JP = {"unanswered": "未取得", "on_hold": "保留中", "take_home": "持ち帰り", "resolved": "聞けた"}
JP_ORDER = ["未取得", "保留中", "持ち帰り", "聞けた"]
EN = {v: k for k, v in JP.items()}

# ==============================
# インライン状態表示（暗転なし）
# ==============================
@contextmanager
def inline_status(label: str = "処理中…"):
    holder = st.empty()
    holder.markdown(f"🛰️ {label}")
    try:
        yield
    finally:
        holder.empty()

# ==============================
# 小ユーティリティ
# ==============================
def _to_int_priority(p: Any) -> int:
    try:
        val = float(p)
        return int(round(val * 100)) if val <= 1.0 else int(round(val))
    except (ValueError, TypeError):
        return 0

def _all_tags(qs: List[Dict[str, Any]]) -> List[str]:
    tags = set()
    for q in qs:
        for t in (q.get("tags") or []):
            tags.add(t)
    return sorted(list(tags))