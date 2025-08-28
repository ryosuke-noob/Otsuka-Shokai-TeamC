from __future__ import annotations
from typing import List, Dict
from difflib import SequenceMatcher

def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()

def dedup_questions(qs: List[Dict], threshold: float=0.9) -> List[Dict]:
    out=[]
    for q in qs:
        t=q.get("text","")
        if any(_sim(t, x.get("text","")) >= threshold for x in out): continue
        out.append(q)
    return out
