from __future__ import annotations
import os, json, requests
from typing import Any, Dict, List
from urllib.parse import urlencode

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")

def _headers() -> Dict[str, str]:
    key = SUPABASE_ANON_KEY or ""
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Prefer": "return=representation",
    }

def _url(table: str) -> str:
    if not SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL が未設定です (.env を確認)")
    return f"{SUPABASE_URL}/rest/v1/{table}"

def select(table: str, params: Dict[str, str]) -> List[Dict[str, Any]]:
    q = urlencode(params, doseq=True)
    r = requests.get(f"{_url(table)}?{q}", headers=_headers(), timeout=30)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []

def insert(table: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    r = requests.post(_url(table), headers=_headers(), data=json.dumps(payload), timeout=30)
    r.raise_for_status()
    return r.json() if r.text else []

def bulk_insert(table: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    r = requests.post(_url(table), headers=_headers(), data=json.dumps(rows), timeout=30)
    r.raise_for_status()
    return r.json() if r.text else []

def patch(table: str, filters: Dict[str, str], payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    q = urlencode(filters, doseq=True)
    r = requests.patch(f"{_url(table)}?{q}", headers=_headers(), data=json.dumps(payload), timeout=30)
    r.raise_for_status()
    return r.json() if r.text else []

class SupaAPI:
    # 既存の __init__, _headers, select/insert/patch などはそのまま

    def bulk_insert(self, table: str, rows: list[dict], prefer_minimal: bool = True):
        """
        rows: [{...}, ...] を一括挿入。大量insertで高速化。
        """
        url = f"{self.base}/rest/v1/{table}"
        headers = self._headers()
        if prefer_minimal:
            headers["Prefer"] = "return=minimal"  # レスポンス軽量化
        r = requests.post(url, json=rows, headers=headers)
        r.raise_for_status()
        return r.json() if not prefer_minimal else []

    def patch_many(self, table: str, rows: list[tuple[dict, dict]]):
        """
        rows: [({条件dict}, {更新dict}), ...]
        条件は eq. 形式の where に変換する簡易版（件数が多過ぎるなら個別 patch を推奨）
        """
        out = []
        for cond, body in rows:
            out.append(self.patch(table, cond, body))
        return out


