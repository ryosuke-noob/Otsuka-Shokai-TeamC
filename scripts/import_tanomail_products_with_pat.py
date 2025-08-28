import os
import sys
from typing import Any, Dict, List

import requests
import pandas as pd

# Reuse transformation helpers from the base importer
from scripts.import_tanomail_products import (
    row_to_product,
    load_csv,
)


PROJECT_ID = "ubnpjirjjzfbhzmgbygw"


def get_service_role_key_from_pat() -> Dict[str, str]:
    pat = os.getenv("SUPABASE_ACCESS_TOKEN")
    if not pat:
        print("SUPABASE_ACCESS_TOKEN is not set.", file=sys.stderr)
        sys.exit(2)

    headers = {"Authorization": f"Bearer {pat}"}
    # Management API
    resp = requests.get(
        f"https://api.supabase.com/v1/projects/{PROJECT_ID}/api-keys",
        headers=headers,
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"Failed to fetch api keys: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(3)
    keys = resp.json()
    service = next((k for k in keys if k.get("role") == "service_role"), None)
    if not service:
        print("service_role key not found in response.", file=sys.stderr)
        sys.exit(4)
    return {
        "service_role_key": service["api_key"],
        "base_url": f"https://{PROJECT_ID}.supabase.co",
    }


def insert_products(base_url: str, service_role_key: str, rows: List[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    url = f"{base_url}/rest/v1/products"
    headers = {
        "Content-Type": "application/json",
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Prefer": "return=representation",
    }
    # Insert in pages of 500
    total = 0
    for i in range(0, len(rows), 500):
        batch = rows[i : i + 500]
        r = requests.post(url, headers=headers, json=batch, timeout=60)
        if not r.ok:
            raise RuntimeError(f"Insert failed at {i}: HTTP {r.status_code} {r.text[:500]}")
        total += len(r.json())
    return total


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Import Tanomail PC list using PAT → service role")
    parser.add_argument(
        "--csv",
        default=os.path.join("data", "tanomail_pc_list.csv"),
        help="Path to the CSV file",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # Prepare rows
    df: pd.DataFrame = load_csv(args.csv)
    if df.empty:
        print("CSV is empty; nothing to import.")
        return

    rows: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        product = row_to_product(row)
        if not product["name"]:
            continue
        rows.append(product)
    print(f"Prepared {len(rows)} product rows.")

    if args.dry_run:
        return

    # Resolve keys via PAT and insert
    cfg = get_service_role_key_from_pat()
    inserted = insert_products(cfg["base_url"], cfg["service_role_key"], rows)
    print(f"Inserted {inserted} rows into public.products.")


if __name__ == "__main__":
    main()



