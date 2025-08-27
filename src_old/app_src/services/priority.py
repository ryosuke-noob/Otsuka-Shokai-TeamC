from __future__ import annotations
from typing import List, Dict, Any

def temperature_from_transcript(last_utterances: List) -> float:
    # 超簡易: 発話件数で0.2〜0.9を返すダミー
    n = len(last_utterances) or 1
    return max(0.2, min(0.9, 0.2 + 0.05*n))

def recompute_priorities(questions: List[Dict[str, Any]], *, stage: str, temperature: float, profile: Dict[str,Any], transcript: List[str]) -> List[Dict[str,Any]]:
    # とりあえず status=unanswered を優遇 + 既存 priority を微調整
    for q in questions:
        base = float(q.get("priority") or 0.5)
        if q.get("status") == "unanswered":
            base += 0.1
        base += (temperature - 0.5) * 0.1
        q["priority"] = max(0.0, min(1.0, base))
    return questions
