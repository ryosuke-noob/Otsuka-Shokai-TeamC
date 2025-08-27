# from __future__ import annotations
# from datetime import datetime
# from typing import Any, Dict, List, Tuple, Optional
# from . import api

# # 互換API: 既存UIから呼ばれる関数群。DB_PATH は互換のためのダミー引数。

# # ---------- bootstrap ----------
# def init_db(_db_path=None) -> None:
#     # Supabase では初期化不要
#     return None

# def seed_if_empty(_db_path=None, _scenario_dir=None) -> None:
#     # 顧客 or 会話が空ならデモデータを1件だけ投入
#     customers = api.select("customers", {"select":"id,name", "limit":"1"})
#     if not customers:
#         api.insert("customers", {"name": "デモ株式会社"})
#     conversations = api.select("conversations", {"select":"id,title", "limit":"1"})
#     if not conversations:
#         api.insert("conversations", {"title": "初回商談（デモ）", "customer_company": "デモ株式会社"})
#     return None

# # ---------- customers ----------
# def list_customers(_db_path=None) -> List[Dict[str, Any]]:
#     rows = api.select("customers", {"select":"id,name,updated_at,created_at", "order":"updated_at.desc"})
#     return rows

# # def get_customer(_db_path, customer_id: str) -> Dict[str, Any]:
# #     rows = api.select("customers", {"select":"id,name,industry,size,usecase,kpi,budget_upper,deadline,constraints,updated_at", "id":f"eq.{customer_id}", "limit":"1"})
# #     return rows[0] if rows else {}

# def get_customer(_db_path, customer_id: str) -> Dict[str, Any]:
#     rows = api.select("customers", {
#         "select": "id,name,kana_name,phone,email,notes,updated_at",
#         "id": f"eq.{customer_id}",
#         "limit": "1",
#     })
#     row = rows[0] if rows else {}
#     # notes にJSONで拡張項目が入っていれば展開（無ければ空）
#     extra = {}
#     try:
#         if row.get("notes"):
#             import json
#             extra = json.loads(row["notes"])
#     except Exception:
#         extra = {}
#     # UI が参照するキーは埋めて返す（存在しないなら空文字）
#     return {
#         "id": row.get("id"),
#         "name": row.get("name",""),
#         "industry": extra.get("industry",""),
#         "size": extra.get("size",""),
#         "usecase": extra.get("usecase",""),
#         "kpi": extra.get("kpi",""),
#         "budget_upper": extra.get("budget_upper",""),
#         "deadline": extra.get("deadline",""),
#         "constraints": extra.get("constraints",""),
#     }

# # def upsert_customer(_db_path, payload: Dict[str, Any]) -> str:
# #     # id があれば PATCH、無ければ INSERT
# #     cid = payload.get("id")
# #     body = {k:v for k,v in payload.items() if k!="id"}
# #     if cid:
# #         rows = api.patch("customers", {"id":f"eq.{cid}"}, body)
# #         return rows[0]["id"] if rows else cid
# #     else:
# #         rows = api.insert("customers", body)
# #         return rows[0]["id"] if rows else ""

# def upsert_customer(_db_path, payload: Dict[str, Any]) -> str:
#     cid = payload.get("id")
#     # customers に実在する列のみ
#     body = {
#         "name": payload.get("name",""),
#         # 必要なら以下も採用（スキーマにある場合のみ）
#         # "kana_name": payload.get("kana_name"),
#         # "phone": payload.get("phone"),
#         # "email": payload.get("email"),
#         # 追加項目は notes にJSONで保存
#         "notes": __pack_extra_notes(payload),
#     }
#     if cid:
#         rows = api.patch("customers", {"id": f"eq.{cid}"}, body)
#         return rows[0]["id"] if rows else cid
#     else:
#         rows = api.insert("customers", body)
#         return rows[0]["id"] if rows else ""

# def __pack_extra_notes(p):
#     import json
#     extra = {
#         "industry": p.get("industry",""),
#         "size": p.get("size",""),
#         "usecase": p.get("usecase",""),
#         "kpi": p.get("kpi",""),
#         "budget_upper": p.get("budget_upper",""),
#         "deadline": p.get("deadline",""),
#         "constraints": p.get("constraints",""),
#     }
#     return json.dumps(extra, ensure_ascii=False)

# # ---------- conversations (meetings) ----------
# def _customer_name(customer_id: Optional[str]) -> Optional[str]:
#     if not customer_id: return None
#     row = get_customer(None, customer_id)
#     return row.get("name")

# def list_meetings(_db_path, customer_id: Optional[str]) -> List[Dict[str, Any]]:
#     # conversations.customer_id が無い前提: customer_company で照合
#     cname = _customer_name(customer_id)
#     params = {"select":"id,title,started_at,updated_at,customer_company", "order":"updated_at.desc"}
#     if cname:
#         params["customer_company"] = f"eq.{cname}"
#     rows = api.select("conversations", params)
#     # UI 表示用フィールド
#     out = []
#     for r in rows:
#         started = r.get("started_at") or r.get("updated_at")
#         date_str = (started or "")[:10] if isinstance(started, str) else ""
#         out.append({"id": r["id"], "title": r.get("title","商談"), "meeting_date": date_str})
#     return out

# def new_meeting(_db_path, customer_id: Optional[str], title: str) -> str:
#     cname = _customer_name(customer_id) or ""
#     rows = api.insert("conversations", {"title": title, "customer_company": cname})
#     return rows[0]["id"] if rows else ""

# # ---------- transcripts / notes ----------
# def get_meeting_bundle(_db_path, meeting_id: Optional[str]) -> Dict[str, Any]:
#     if not meeting_id:
#         return {"transcript": [], "questions": [], "notes": []}
#     logs = api.select("transcripts", {
#         "select":"id,transcript_text,created_at",
#         "conversation_id": f"eq.{meeting_id}",
#         "order":"created_at.asc",
#         "limit":"500"
#     })
#     # transcript: [(HH:MM:SS, text)]
#     transcript = []
#     for r in logs:
#         ts = r.get("created_at","")
#         hhmmss = ts[11:19] if isinstance(ts, str) and len(ts)>=19 else ""
#         transcript.append((hhmmss, r.get("transcript_text","")))

#     qs = api.select("questions", {
#         "select":"id,question_text,status,priority,created_at,updated_at,question_tags(tags:tags(id,name))",
#         "conversation_id": f"eq.{meeting_id}",
#         "order":"created_at.asc"
#     })
#     questions = []
#     for q in qs:
#         questions.append({
#             "id": q["id"],
#             "text": q.get("question_text",""),
#             "tags": [t["name"] for t in (q.get("question_tags") or [])],
#             "role": "—",
#             "priority": float(q.get("priority") or 0) / 100.0 if isinstance(q.get("priority"), int) else float(q.get("priority") or 0),
#             "status": q.get("status","unanswered"),
#         })

#     notes = api.select("notes", {
#         "select":"id,content,created_at",
#         "conversation_id": f"eq.{meeting_id}",
#         "order":"created_at.asc"
#     })

#     return {"transcript": transcript, "questions": questions, "notes": notes}

# def add_transcript_line(_db_path, meeting_id: str, ts_hhmmss: str, role: str, text: str) -> None:
#     prefix = f"[{role}] " if role else ""
#     api.insert("transcripts", {"conversation_id": meeting_id, "transcript_text": f"{prefix}{text}"})
#     return None

# def add_note(_db_path, meeting_id: str, content: str) -> None:
#     api.insert("notes", {"conversation_id": meeting_id, "content": content})
#     return None

# # ---------- questions / tags / answers ----------
# def upsert_questions(_db_path, meeting_id: str, questions: List[Dict[str, Any]]) -> None:
#     """UIの質問配列を Supabase に反映（insert or patch）。tags も可能なら付与。"""
#     for q in questions:
#         qid = q.get("id")
#         payload = {
#             "conversation_id": meeting_id,
#             "question_text": q.get("text",""),
#             "status": q.get("status","unanswered"),
#         }
#         pri = q.get("priority")
#         if pri is not None:
#             # UIは 0.0~1.0 の想定。DBは 0~100 を推奨。
#             payload["priority"] = int(round(float(pri) * 100)) if isinstance(pri, (int,float)) and float(pri) <= 1.0 else pri
#         if qid:
#             api.patch("questions", {"id": f"eq.{qid}"}, payload)
#         else:
#             created = api.insert("questions", payload)
#             if created:
#                 q["id"] = created[0]["id"]

#         # タグ付与
#         tags = q.get("tags") or []
#         if tags:
#             _ensure_tags_and_link(q["id"], tags)

# def update_question(question_id: str, *, status: Optional[str]=None, priority: Optional[int]=None) -> None:
#     payload = {}
#     if status is not None:
#         payload["status"] = status
#     if priority is not None:
#         payload["priority"] = priority
#     if payload:
#         api.patch("questions", {"id": f"eq.{question_id}"}, payload)

# def _ensure_tags_and_link(question_id: str, tag_names: List[str]) -> None:
#     # 既存タグ取得
#     all_tags = api.select("tags", {"select":"id,name", "order":"created_at.asc"})
#     name2id = {t["name"]: t["id"] for t in all_tags}
#     need_create = [n for n in tag_names if n not in name2id]
#     # 作成
#     for n in need_create:
#         rows = api.insert("tags", {"name": n})
#         if rows: name2id[n] = rows[0]["id"]
#     # リンク作成（重複はPK衝突で自動スキップ）
#     rows = [{"question_id": question_id, "tag_id": name2id[n]} for n in tag_names if n in name2id]
#     if rows:
#         try:
#             api.bulk_insert("question_tags", rows)
#         except Exception:
#             pass

# app_src/services/supabase_db.py
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from . import api
import json

# -----------------------------------------------------------------------------
# 互換API: 既存UIから呼ばれる関数群。DB_PATH は互換のためのダミー引数。
# -----------------------------------------------------------------------------

# ---------- bootstrap ----------
def init_db(_db_path: Optional[str] = None) -> None:
    # Supabase では初期化不要
    return None

def seed_if_empty(_db_path: Optional[str] = None, _scenario_dir: Optional[str] = None) -> None:
    # 顧客 or 会話が空ならデモデータを1件だけ投入
    customers = api.select("customers", {"select": "id,name", "limit": "1"})
    if not customers:
        api.insert("customers", {"name": "デモ株式会社"})
    conversations = api.select("conversations", {"select": "id,title", "limit": "1"})
    if not conversations:
        api.insert("conversations", {"title": "初回商談（デモ）", "customer_company": "デモ株式会社"})
    return None

# ---------- customers ----------
def list_customers(_db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    rows = api.select(
        "customers",
        {"select": "id,name,updated_at,created_at", "order": "updated_at.desc"}
    )
    return rows or []

def get_customer(_db_path: Optional[str], customer_id: str) -> Dict[str, Any]:
    rows = api.select(
        "customers",
        {
            "select": "id,name,kana_name,phone,email,notes,updated_at",
            "id": f"eq.{customer_id}",
            "limit": "1",
        },
    )
    row = rows[0] if rows else {}
    # notes に JSON で拡張項目が入っていれば展開
    extra = {}
    try:
        if row.get("notes"):
            extra = json.loads(row["notes"])
    except Exception:
        extra = {}

    return {
        "id": row.get("id"),
        "name": row.get("name", ""),
        "industry": extra.get("industry", ""),
        "size": extra.get("size", ""),
        "usecase": extra.get("usecase", ""),
        "kpi": extra.get("kpi", ""),
        "budget_upper": extra.get("budget_upper", ""),
        "deadline": extra.get("deadline", ""),
        "constraints": extra.get("constraints", ""),
    }

def __pack_extra_notes(p: Dict[str, Any]) -> str:
    extra = {
        "industry": p.get("industry", ""),
        "size": p.get("size", ""),
        "usecase": p.get("usecase", ""),
        "kpi": p.get("kpi", ""),
        "budget_upper": p.get("budget_upper", ""),
        "deadline": p.get("deadline", ""),
        "constraints": p.get("constraints", ""),
    }
    return json.dumps(extra, ensure_ascii=False)

def upsert_customer(_db_path: Optional[str], payload: Dict[str, Any]) -> str:
    cid = payload.get("id")
    # customers テーブルに実在する列のみ保存。拡張は notes(JSON)
    body = {
        "name": payload.get("name", ""),
        "notes": __pack_extra_notes(payload),
    }
    if cid:
        rows = api.patch("customers", {"id": f"eq.{cid}"}, body)
        return rows[0]["id"] if rows else cid
    else:
        rows = api.insert("customers", body)
        return rows[0]["id"] if rows else ""

# ---------- conversations (meetings) ----------
def _customer_name(customer_id: Optional[str]) -> Optional[str]:
    if not customer_id:
        return None
    row = get_customer(None, customer_id)
    return row.get("name")

def list_meetings(_db_path: Optional[str], customer_id: Optional[str]) -> List[Dict[str, Any]]:
    # conversations.customer_id が無い前提: customer_company で照合
    cname = _customer_name(customer_id)
    params: Dict[str, str] = {
        "select": "id,title,started_at,updated_at,customer_company",
        "order": "updated_at.desc",
    }
    if cname:
        params["customer_company"] = f"eq.{cname}"
    rows = api.select("conversations", params) or []

    out: List[Dict[str, Any]] = []
    for r in rows:
        started = r.get("started_at") or r.get("updated_at")
        if isinstance(started, str) and len(started) >= 10:
            date_str = started[:10]
        else:
            date_str = ""
        out.append(
            {
                "id": r["id"],
                "title": r.get("title", "商談"),
                "meeting_date": date_str,
            }
        )
    return out

def new_meeting(_db_path: Optional[str], customer_id: Optional[str], title: str) -> str:
    cname = _customer_name(customer_id) or ""
    rows = api.insert("conversations", {"title": title, "customer_company": cname})
    return rows[0]["id"] if rows else ""

# ---------- transcripts / notes ----------
def get_meeting_bundle(_db_path: Optional[str], meeting_id: Optional[str]) -> Dict[str, Any]:
    if not meeting_id:
        return {"transcript": [], "questions": [], "notes": []}

    # transcripts: 書き起こしを時系列で
    logs = api.select(
        "transcripts",
        {
            "select": "id,transcript_text,created_at",
            "conversation_id": f"eq.{meeting_id}",
            "order": "created_at.asc",
            "limit": "500",
        },
    ) or []

    transcript: List[Tuple[str, str]] = []
    for r in logs:
        ts = r.get("created_at", "")
        hhmmss = ts[11:19] if isinstance(ts, str) and len(ts) >= 19 else ""
        transcript.append((hhmmss, r.get("transcript_text", "")))

    # questions: リレーションで question_tags(tags:tags(id,name)) を引く
    qs = api.select(
        "questions",
        {
            "select": "id,question_text,status,priority,created_at,updated_at,question_tags(tags:tags(id,name))",
            "conversation_id": f"eq.{meeting_id}",
            "order": "created_at.asc",
        },
    ) or []

    def _extract_tag_names(qrow: Dict[str, Any]) -> List[str]:
        names: List[str] = []
        for qt in (qrow.get("question_tags") or []):
            # パターンA: {"name": "..."} で返る場合（ビュー等の都合）
            if isinstance(qt, dict) and "name" in qt and isinstance(qt["name"], str):
                names.append(qt["name"])
                continue
            # パターンB: {"tags": {"id": "...", "name": "..."}} で返る場合（標準の埋め込み）
            if isinstance(qt, dict) and "tags" in qt and isinstance(qt["tags"], dict):
                nm = qt["tags"].get("name")
                if isinstance(nm, str):
                    names.append(nm)
        # 重複除去・順序維持
        seen = set()
        out = []
        for n in names:
            if n not in seen:
                seen.add(n)
                out.append(n)
        return out

    questions: List[Dict[str, Any]] = []
    for q in qs:
        # priority: DB(0-100) or 浮動小数が来ても UI(0.0-1.0) に変換して返す
        p_raw = q.get("priority")
        if p_raw is None:
            p_ui = 0.0
        else:
            try:
                p_val = float(p_raw)
                p_ui = p_val / 100.0 if p_val > 1.0 else p_val
            except Exception:
                p_ui = 0.0

        questions.append(
            {
                "id": q["id"],
                "text": q.get("question_text", ""),
                "tags": _extract_tag_names(q),
                "role": "—",
                "priority": p_ui,
                "status": q.get("status", "unanswered"),
            }
        )

    notes = api.select(
        "notes",
        {
            "select": "id,content,created_at",
            "conversation_id": f"eq.{meeting_id}",
            "order": "created_at.asc",
        },
    ) or []

    return {"transcript": transcript, "questions": questions, "notes": notes}

def add_transcript_line(_db_path: Optional[str], meeting_id: str, ts_hhmmss: str, role: str, text: str) -> None:
    prefix = f"[{role}] " if role else ""
    api.insert("transcripts", {"conversation_id": meeting_id, "transcript_text": f"{prefix}{text}"})
    return None

def add_note(_db_path: Optional[str], meeting_id: str, content: str) -> None:
    api.insert("notes", {"conversation_id": meeting_id, "content": content})
    return None

# ---------- questions / tags / answers ----------
def _normalize_status(s: Optional[str]) -> str:
    """
    DB enum: unanswered / take_home / answered
    UI は resolved / on_hold などを使うことがあるため正規化する。
    """
    if not s:
        return "unanswered"
    s = s.strip().lower()
    if s in ("unanswered", "take_home", "answered"):
        return s
    if s == "resolved":
        return "answered"
    if s == "on_hold":
        # enum に無いため、一旦 unanswered として保存（UI側では on_hold はメモリで扱う想定）
        return "unanswered"
    # 不明値もフェイルセーフで unanswered
    return "unanswered"

def _to_db_priority(v: Any) -> Optional[int]:
    """
    UI(0.0-1.0) or DB(0-100) どちらでも受け取り、DB保存用(0-100 int)に変換。
    """
    if v is None:
        return None
    try:
        f = float(v)
        if f <= 1.0:
            return int(round(f * 100))
        return int(round(f))
    except Exception:
        return None

def upsert_questions(_db_path: Optional[str], meeting_id: str, questions: List[Dict[str, Any]]) -> None:
    """UIの質問配列を Supabase に反映（insert or patch）。tags も可能なら付与。"""
    for q in questions:
        qid = q.get("id")
        payload: Dict[str, Any] = {
            "conversation_id": meeting_id,
            "question_text": q.get("text", ""),
            "status": _normalize_status(q.get("status")),
        }
        pri = _to_db_priority(q.get("priority"))
        if pri is not None:
            payload["priority"] = pri

        if qid:
            api.patch("questions", {"id": f"eq.{qid}"}, payload)
        else:
            created = api.insert("questions", payload)
            if created:
                q["id"] = created[0]["id"]

        # タグ付与
        tags = q.get("tags") or []
        if tags and q.get("id"):
            _ensure_tags_and_link(q["id"], tags)

def update_question(question_id: str, *, status: Optional[str] = None, priority: Optional[int] = None) -> None:
    payload: Dict[str, Any] = {}
    if status is not None:
        payload["status"] = _normalize_status(status)
    if priority is not None:
        payload["priority"] = _to_db_priority(priority)
    if payload:
        api.patch("questions", {"id": f"eq.{question_id}"}, payload)

def _ensure_tags_and_link(question_id: str, tag_names: List[str]) -> None:
    # 既存タグ取得
    all_tags = api.select("tags", {"select": "id,name", "order": "created_at.asc"}) or []
    name2id = {t["name"]: t["id"] for t in all_tags if "name" in t and "id" in t}

    # 未作成のタグを作成
    need_create = [n for n in tag_names if n not in name2id]
    for n in need_create:
        try:
            rows = api.insert("tags", {"name": n})
            if rows:
                name2id[n] = rows[0]["id"]
        except Exception:
            # ユニーク制約競合などは無視して取得し直し
            latest = api.select("tags", {"select": "id,name", "name": f"eq.{n}", "limit": "1"}) or []
            if latest:
                name2id[n] = latest[0]["id"]

    # question_tags リンク作成（重複はPK衝突でスキップ）
    link_rows = [{"question_id": question_id, "tag_id": name2id[n]} for n in tag_names if n in name2id]
    if link_rows:
        try:
            api.bulk_insert("question_tags", link_rows)
        except Exception:
            # 一括失敗時は1件ずつベストエフォートで
            for r in link_rows:
                try:
                    api.insert("question_tags", r)
                except Exception:
                    pass
