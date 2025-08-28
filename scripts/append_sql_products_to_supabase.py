import os
import re
import sys
import json
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv

INSERT_RE = re.compile(r"^insert into public\.products\s*\(name,\s*cost,\s*category,\s*brand,\s*description\) values \((.*)\);\s*$", re.IGNORECASE)


def split_values(inner: str) -> List[str]:
    parts: List[str] = []
    buf: List[str] = []
    in_str = False
    i = 0
    while i < len(inner):
        ch = inner[i]
        if in_str:
            if ch == "'":
                if i + 1 < len(inner) and inner[i + 1] == "'":
                    buf.append("'")
                    i += 2
                    continue
                in_str = False
                buf.append(ch)
                i += 1
                continue
            buf.append(ch)
            i += 1
            continue
        if ch == "'":
            in_str = True
            buf.append(ch)
            i += 1
            continue
        if ch == ",":
            parts.append("".join(buf).strip())
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    if buf:
        parts.append("".join(buf).strip())
    return parts


def unquote(sql_literal: str) -> str:
    s = sql_literal.strip()
    if s.lower() == "null":
        return None  # type: ignore
    if s.startswith("'") and s.endswith("'"):
        return s[1:-1].replace("''", "'")
    return s


def parse_insert_line(line: str) -> Dict[str, Any]:
    m = INSERT_RE.match(line.strip())
    if not m:
        raise ValueError("not an insert line")
    inner = m.group(1)
    fields = split_values(inner)
    if len(fields) != 5:
        raise ValueError("unexpected values count")
    name = unquote(fields[0])
    cost_raw = fields[1].strip()
    cost = None
    try:
        cost = int(cost_raw) if cost_raw.lower() != "null" else None
    except Exception:
        cost = None
    category = unquote(fields[2])
    brand = unquote(fields[3])
    description = unquote(fields[4])
    return {
        "name": name,
        "cost": cost,
        "category": category,
        "brand": brand,
        "description": description,
    }


def read_inserts(sql_path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with open(sql_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.lower().startswith("insert into public.products"):
                continue
            try:
                row = parse_insert_line(line)
            except Exception:
                continue
            if not row.get("name"):
                continue
            rows.append(row)
    return rows


def rest_select_count(base_url: str, key: str) -> int:
    url = f"{base_url}/rest/v1/products?select=count"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept-Profile": "public",
        "Content-Profile": "public",
        "Prefer": "count=exact",
    }
    resp = requests.get(url, headers=headers, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"Count failed: {resp.status_code} {resp.text[:300]}")
    # Supabase returns count in Content-Range header when Prefer count=exact
    cr = resp.headers.get("Content-Range", "0/0")
    try:
        after_slash = cr.split("/")[-1]
        return int(after_slash)
    except Exception:
        # fallback to len response if representation
        try:
            data = resp.json()
            return len(data) if isinstance(data, list) else 0
        except Exception:
            return 0


def rest_insert(base_url: str, key: str, rows: List[Dict[str, Any]], batch_size: int = 500) -> int:
    url = f"{base_url}/rest/v1/products"
    headers = {
        "Content-Type": "application/json",
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Prefer": "return=representation",
        "Accept-Profile": "public",
        "Content-Profile": "public",
    }
    total = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        resp = requests.post(url, headers=headers, json=batch, timeout=120)
        if not resp.ok:
            raise RuntimeError(f"Insert failed: HTTP {resp.status_code} {resp.text[:500]}")
        data = resp.json()
        total += len(data) if isinstance(data, list) else 0
    return total


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Append products from SQL into Supabase via REST")
    parser.add_argument("--sql", default=os.path.join("data", "products_seed_enriched.sql"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # Load .env if present
    load_dotenv()

    rows = read_inserts(args.sql)
    print(f"Parsed {len(rows)} insert rows from SQL.")

    base_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    if args.dry_run:
        print("Dry run: skipping insert.")
        return

    if not base_url or not key:
        print("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
        sys.exit(2)

    before = rest_select_count(base_url, key)
    print(f"Existing products count: {before}")

    inserted = rest_insert(base_url, key, rows)
    after = rest_select_count(base_url, key)
    print(json.dumps({"inserted": inserted, "before": before, "after": after}, ensure_ascii=False))


if __name__ == "__main__":
    main()
