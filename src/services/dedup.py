from __future__ import annotations
from typing import List, Dict, Any
from difflib import SequenceMatcher

def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

def dedup_questions(questions: List[Dict[str,Any]], threshold: float = 0.88) -> List[Dict[str,Any]]:
    out = []
    for q in questions:
        txt = (q.get("text") or "").strip()
        if not txt: 
            continue
        if any(_sim(txt.lower(), x.get("text","").lower()) >= threshold for x in out):
            continue
        out.append(q)
    return out
