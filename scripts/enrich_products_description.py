import os
import re
import sys
import html
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup


SQL_INSERT_PREFIX = "insert into public.products (name, cost, category, brand, description) values ("


@dataclass
class ProductRow:
    raw_prefix: str
    name: str
    cost: Optional[int]
    category: str
    brand: str
    description: str
    raw_suffix: str


def _split_sql_values(values_section: str) -> List[str]:
    """
    Split a SQL VALUES(...) inner section by commas while respecting single-quoted
    strings and escaped quotes ('' → single quote in SQL). Returns the 5 fields as strings.
    """
    parts: List[str] = []
    buf: List[str] = []
    in_str = False
    i = 0
    while i < len(values_section):
        ch = values_section[i]
        if in_str:
            if ch == "'":
                # handle escaped single quote in SQL: ''
                if i + 1 < len(values_section) and values_section[i + 1] == "'":
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
        # not in string
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


def parse_insert_line(line: str) -> Optional[ProductRow]:
    if not line.lower().startswith(SQL_INSERT_PREFIX):
        return None
    # Keep prefix/suffix to preserve formatting
    prefix_end = line.find("(")
    # values(
    values_start = line.find("(", prefix_end + 1)
    values_end = line.rfind(")")
    if values_start == -1 or values_end == -1:
        return None
    raw_prefix = line[: values_start + 1]
    raw_suffix = line[values_end:]

    values_inner = line[values_start + 1 : values_end]
    fields = _split_sql_values(values_inner)
    if len(fields) != 5:
        return None

    # Each field is either 'text' or numeric/null. Strip outer quotes if present.
    def unquote(sql_literal: str) -> str:
        s = sql_literal.strip()
        if s.startswith("'") and s.endswith("'"):
            inner = s[1:-1].replace("''", "'")
            return inner
        return s

    name = unquote(fields[0])
    cost_str = fields[1].strip()
    cost: Optional[int]
    try:
        cost = int(cost_str) if cost_str.lower() != "null" else None
    except Exception:
        cost = None
    category = unquote(fields[2])
    brand = unquote(fields[3])
    description = unquote(fields[4])
    return ProductRow(raw_prefix=raw_prefix, name=name, cost=cost, category=category, brand=brand, description=description, raw_suffix=raw_suffix)


def extract_product_url(description_text: str) -> Optional[str]:
    # Expect pattern like "商品URL: https://... / 一覧URL: ..."
    # Grab the first http(s) URL after 商品URL:
    m = re.search(r"商品URL\s*:\s*(https?://\S+)", description_text)
    if m:
        # strip trailing separators like "/", "(", or spaces
        url = m.group(1)
        # Some lines include trailing '/' or parameters followed by spaces then '/'
        # Keep as-is; downstream requests can handle
        return url
    return None


def fetch_description_from_page(url: str, timeout_sec: int = 20) -> Optional[str]:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; description-bot/1.0)"}
        resp = requests.get(url, headers=headers, timeout=timeout_sec)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        # Heuristics for Tanomail product pages: try typical description areas
        candidates: List[str] = []
        # Common meta description
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            candidates.append(meta_desc["content"].strip())
        # Elements that likely hold description
        for sel in [
            "div#product-detail",
            "div.product-detail",
            "section.product-detail",
            "div.item-detail",
            "div#item-detail",
            "div#product",
            "article",
        ]:
            node = soup.select_one(sel)
            if node:
                text = " ".join(node.get_text(" ", strip=True).split())
                if text:
                    candidates.append(text)

        # Fallback: longest paragraph on page
        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        if paragraphs:
            longest = max(paragraphs, key=lambda t: len(t))
            if longest:
                candidates.append(longest)

        # Return concatenated candidate text (raw) for downstream summarization
        text = "\n".join(dict.fromkeys([c for c in candidates if c]))
        if not text:
            return None
        return text
    except Exception:
        return None


def rebuild_insert_line(row: ProductRow, new_description: str) -> str:
    # Escape single quotes for SQL
    esc = new_description.replace("'", "''")
    # Keep original prefix/suffix and replace only the last field content
    # We reconstruct the values with proper quoting for all text fields.
    name_sql = f"'{row.name.replace("'", "''")}'"
    category_sql = f"'{row.category.replace("'", "''")}'"
    brand_sql = f"'{row.brand.replace("'", "''")}'"
    desc_sql = f"'{esc}'"
    cost_sql = "null" if row.cost is None else str(row.cost)
    return f"{row.raw_prefix}{name_sql}, {cost_sql}, {category_sql}, {brand_sql}, {desc_sql}{row.raw_suffix}"


def iter_insert_lines(lines: Iterable[str]) -> Iterable[Tuple[int, ProductRow]]:
    for idx, line in enumerate(lines):
        line_stripped = line.strip()
        if not line_stripped.lower().startswith("insert into public.products"):
            continue
        parsed = parse_insert_line(line_stripped)
        if parsed:
            yield idx, parsed


def sentence_split_jp(text: str) -> List[str]:
    # Simple splitter for Japanese sentences
    # Keep punctuation marks attached
    sentences: List[str] = []
    buf: List[str] = []
    for ch in text:
        buf.append(ch)
        if ch in ("。", "！", "？"):
            s = "".join(buf).strip()
            if s:
                sentences.append(s)
            buf = []
    # tail
    tail = "".join(buf).strip()
    if tail:
        sentences.append(tail)
    # Also split on newlines as fallback
    normalized: List[str] = []
    for s in sentences:
        normalized.extend([p.strip() for p in s.split("\n") if p.strip()])
    return normalized or [text]


def clean_boilerplate(text: str) -> str:
    # Remove repetitive site boilerplate and commerce-only fragments
    patterns = [
        r"画像をクリックすると拡大表示します",
        r"法人限定",
        r"比較表に追加",
        r"商品を比較する",
        r"おすすめ商品",
        r"メーカー直送品",
        r"お申込番号",
        r"提供価格.*?円",
        r"税込",
        r"税抜",
        r"在庫状況",
        r"お届け",
        r"本体メニュー",
        r"基本スペック",
        r"カート",
        r"レビュー",
        r"チェック",
        r"商品一覧",
        r"お問い合わせ",
        r"注意事項",
    ]
    cleaned = text
    for pat in patterns:
        cleaned = re.sub(pat, " ", cleaned)
    # Remove long price-like numbers with 円
    cleaned = re.sub(r"[0-9,]+\s*円", " ", cleaned)
    # Collapse whitespace
    cleaned = " ".join(cleaned.split())
    return cleaned.strip()


def summarize_product_text(raw_text: str, product_name: str, max_chars: int = 240) -> Optional[str]:
    cleaned = clean_boilerplate(raw_text)
    if not cleaned:
        return None
    sentences = sentence_split_jp(cleaned)
    # Filter out low-signal sentences
    def is_informative(s: str) -> bool:
        if len(s) < 8:
            return False
        unwanted = [
            "円", "在庫", "送料", "お届け", "注文", "型番:", "商品URL:", "一覧URL:", "画像:",
            "メニュー", "スペック", "仕様", "カート", "比較", "お問い合わせ",
        ]
        if any(u in s for u in unwanted):
            return False
        return True

    candidates = [s for s in sentences if is_informative(s)]
    if not candidates:
        candidates = sentences

    # Prefer sentences mentioning product or features
    keywords = [
        "AI", "パフォーマンス", "携帯性", "軽量", "堅牢", "バッテリー", "画面", "薄型",
        "Windows", "Core", "Ryzen", "SSD", "セキュリティ", "ビジネス", "モバイル",
    ]
    scored = []
    for s in candidates:
        score = 0
        score += sum(1 for k in keywords if k in s)
        if product_name[:10] in s:
            score += 1
        # Prefer mid-length sentences
        length = len(s)
        if 20 <= length <= 80:
            score += 1
        scored.append((score, -len(s), s))
    scored.sort(reverse=True)

    summary: List[str] = []
    total = 0
    for _, _, s in scored:
        if s in summary:
            continue
        if total + len(s) > max_chars and summary:
            break
        summary.append(s)
        total += len(s)
        if total >= max_chars or len(summary) >= 3:
            break

    text = "".join(summary).strip()
    if not text:
        text = cleaned[:max_chars].rstrip() + ("…" if len(cleaned) > max_chars else "")
    return text


def build_name_to_url_map(source_sql_path: Optional[str]) -> dict:
    mapping = {}
    if not source_sql_path or not os.path.exists(source_sql_path):
        return mapping
    with open(source_sql_path, "r", encoding="utf-8") as f:
        for _i, row in iter_insert_lines(f.readlines()):
            url = extract_product_url(row.description)
            if url:
                mapping[row.name] = url
    return mapping


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Enrich product descriptions by scraping 商品URL")
    parser.add_argument("--input", default=os.path.join("data", "products_seed.sql"))
    parser.add_argument("--output", default=os.path.join("data", "products_seed_enriched.sql"))
    parser.add_argument("--max", type=int, default=0, help="Limit number of rows to process (0=all)")
    parser.add_argument("--only-missing", action="store_true", help="Only enrich if 商品URL exists and description looks auto-generated")
    parser.add_argument("--source-sql", default=os.path.join("data", "products_seed.sql"), help="Optional source SQL to recover 商品URL by product name")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        lines = f.readlines()

    name_to_url = build_name_to_url_map(args.source_sql)
    processed = 0
    for idx, row in iter_insert_lines(lines):
        if args.max and processed >= args.max:
            break
        url = extract_product_url(row.description)
        if not url and row.name in name_to_url:
            url = name_to_url[row.name]
        if not url:
            continue
        # Optionally skip if description already seems natural (heuristic: lacks "型番:" and "商品URL:")
        if args.only_missing:
            if "商品URL:" not in row.description and "型番:" not in row.description:
                continue

        raw_text = fetch_description_from_page(url)
        new_desc = summarize_product_text(raw_text, row.name) if raw_text else None
        if not new_desc:
            continue
        new_line = rebuild_insert_line(row, new_desc)
        lines[idx] = new_line + "\n"
        processed += 1

    with open(args.output, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print(f"Enriched {processed} rows. Wrote: {args.output}")


if __name__ == "__main__":
    main()


