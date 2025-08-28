### Dify × Supabase 接続ハンズオン（チケット分割付き）

本ドキュメントは、Dify と Supabase を接続し、
- products の `cost` を取得（最短で価値を出す）
- pgvector による意味検索（RAG）
を段階的に実装するためのハンズオン資料です。初心者でも迷わず進められるよう、各ステップを「チケット」として分割しています。

---

## 事前準備（超重要・一度だけ）

### 1) Azure OpenAI の準備（gpt-5-mini / text-embedding-3-large）
- 公式ガイド
  - リソース作成: [Microsoft Learn: Azure OpenAI リソースの作成](https://learn.microsoft.com/azure/ai-services/openai/how-to/create-resource)
  - モデルのデプロイ: [Microsoft Learn: モデルのデプロイ](https://learn.microsoft.com/azure/ai-services/openai/how-to/deploy-models)
  -（必要に応じ）利用申請: [aka.ms/oai/access](https://aka.ms/oai/access)

- 手順（ポータル操作・クリック通り）
  1. `https://portal.azure.com` にサインイン
  2. 左上「リソースの作成」→ 検索に「Azure OpenAI」→ サービスを選択 →「作成」
  3. 入力:
     - サブスクリプション／リソースグループ: 選択 or 新規
     - リージョン: 利用可能なリージョン（例: East US／Japan East）
     - 名前: 一意（例: `aoai-teamc`）
     - 価格レベル: Standard S0（既定）
     →「確認および作成」→「作成」
  4. デプロイ完了後、作成したリソースを開く → 左メニュー「モデルのデプロイ」
     -「+ 新しいデプロイの作成」
       - モデル: `gpt-5-mini`、デプロイ名: `gpt-5-mini`
       - 作成を実行
     - 同様に `text-embedding-3-large` をデプロイ（デプロイ名: `text-embedding-3-large`）
  5. 左メニュー「キーとエンドポイント」→ 以下を控える
     - エンドポイント例: `https://<your-aoai>.openai.azure.com`
     - キー: 「キー1」または「キー2」

- 環境変数（本ドキュメントの前提名）
  - `AZURE_OPENAI_ENDPOINT`（例: `https://<your-aoai>.openai.azure.com`）
  - `AZURE_OPENAI_API_KEY`
  - `AZURE_CHAT_DEPLOYMENT` = `gpt-5-mini`
  - `AZURE_EMBEDDING_DEPLOYMENT` = `text-embedding-3-large`

- Windows PowerShell 例（セッション限定）
```powershell
$env:AZURE_OPENAI_ENDPOINT = "https://<your-aoai>.openai.azure.com"
$env:AZURE_OPENAI_API_KEY = "<YOUR_AOAI_KEY>"
$env:AZURE_CHAT_DEPLOYMENT = "gpt-5-mini"
$env:AZURE_EMBEDDING_DEPLOYMENT = "text-embedding-3-large"
```

### 2) Supabase の準備（どこで何が見つかるか）
- 公式ガイド
  - API キー・URL: [Supabase Docs: API Keys / Project API](https://supabase.com/docs/guides/platform/api-keys)
  - DB 接続: [Supabase Docs: Connect to Postgres](https://supabase.com/docs/guides/database/connecting-to-postgres)

- 手順（ダッシュボードの場所）
  1. `https://supabase.com` → サインイン → プロジェクトを開く
  2. 左メニュー「Settings」→「API」
     - Project URL: 例 `https://<PROJECT-REF>.supabase.co`
     - anon key（公開読み取り用）
     - service_role key（サーバー側・高権限。クライアントへ露出しない）
  3. 左メニュー「Settings」→「Database」
     - Host（例: `db.<PROJECT-REF>.supabase.co`）
     - Port（通常 `5432`）
     - Database（例: `postgres`）
     - User（通常 `postgres`）
     - Password（プロジェクト作成時に設定）

- Windows PowerShell 例（セッション限定・必要な場合）
```powershell
$env:SUPABASE_URL = "https://<PROJECT-REF>.supabase.co"
$env:SUPABASE_ANON_KEY = "<YOUR_ANON_KEY>"
$env:SUPABASE_SERVICE_ROLE_KEY = "<YOUR_SERVICE_ROLE_KEY>"  # サーバー側のみ
```

### 3) Dify の準備（モデルプロバイダ設定）
- Dify → Settings → Model Provider → 「Azure OpenAI」を追加
  - Endpoint: `AZURE_OPENAI_ENDPOINT`
  - API Key: `AZURE_OPENAI_API_KEY`
  - Chat: `AZURE_CHAT_DEPLOYMENT`（例: `gpt-5-mini`）
  - Embeddings: `AZURE_EMBEDDING_DEPLOYMENT`（例: `text-embedding-3-large`）
- アプリ作成時にモデルとして `gpt-5-mini` を選べることを確認

## ゴール
- Dify から Supabase の `public.products` を参照して `cost` を取得できる
- （拡張）クエリをベクトル化して `description` に対する意味検索ができる

## どの方式を使う？（重要）
- 単純な表参照・集計の自動化 → Dify の「SQL Database」ツール（または REST 呼び出し）で十分。外部ナレッジAPI（`/retrieval`）は不要。
- 自前のRAG（意味検索）を使って Dify のナレッジに統合 → Dify の「外部ナレッジAPI（`POST /retrieval`）」仕様に沿った API 実装が必要。

---

## ルートA（最短）：SQL で `cost` を取得する

### チケットA-1: Supabase API/接続情報を確認する
- 成果物: Project URL / anon key / DB接続情報（Host, DB, User, Password）をメモ
- 手順:
  1. Supabase ダッシュボード → Settings → API
  2. `Project URL` と `anon key` を控える（ソース管理にコミットしない）
  3. ダッシュボード → Project Home（Connection info）から DB 接続情報を控える

### チケットA-2: Dify の「SQL Database」ツールを接続する（推奨）
- 成果物: Dify から PostgreSQL（Supabase）への接続が成功
- 手順:
  1. Dify → Tools → Add tool → SQL Database
  2. Database type: PostgreSQL
  3. Host: `db.<project-ref>.supabase.co`, Port: `5432`
  4. Database: `postgres`, User: `postgres`, Password:（Supabaseプロジェクト作成時のDBパスワード）
  5. SSL: 有効、Test connection → Save
  6. 成功したら、Tool にわかりやすい名前を付ける（例: `Supabase-Postgres`）
  7. フローエディタでこのツールを選べることを確認

（代替）HTTP リクエストで Supabase REST を直接呼び出す
- 成果物: REST 経由の読み取り成功
- 設定例（Dify の HTTP リクエストブロック）:
  - Method: GET
  - URL: `https://<PROJECT-REF>.supabase.co/rest/v1/products?select=name,cost&name=ilike.*{{ user_query }}*`
  - Headers:
    - `apikey`: `<SUPABASE_ANON_KEY>`
    - `Authorization`: `Bearer <SUPABASE_ANON_KEY>`
    - `Accept`: `application/json`

### チケットA-3: Dify フローに SQL 実行ノードを追加する
- 成果物: 入力に応じて `name, cost` を返すフロー
- クエリ例:
```sql
select name, cost
from public.products
where name ilike '%' || {{ user_query }} || '%'
order by cost asc
limit 10;
```
 - 手順（クリック操作）
   1. Dify でアプリを開く → Flow（または Workflow）
   2. 「+」→ Node 追加 → 「SQL Database」
   3. 接続済みのツール（例: `Supabase-Postgres`）を選択
   4. 上記 SQL を貼り付け、`{{ user_query }}` をユーザー入力に接続
   5. 実行テスト（Run）→ 結果が返ることを確認

### チケットA-4: 動作確認と簡易プロンプト整形
- 成果物: 実行結果の整形（テーブル化や箇条書き）
- 手順: SQL ノードの出力をテンプレートノードや回答ノードで整形

---

## ルートB（RAG）：外部ナレッジAPI `/retrieval` ＋ pgvector で意味検索

### 全体像
1) Supabase に `vector` 拡張・埋め込みカラム・検索 RPC を用意
2) `/retrieval` を実装した API（推奨: Supabase Edge Function）を用意
3) Dify の「外部ナレッジAPI」に登録→アプリから利用

[クライアント(Dify)] → [Edge Function (retrieval/index.ts)]
                     │
                     │ supabase.rpc("match_products", {...})
                     ▼
               [Postgres + pgvector]
               └─ SQL関数 match_products()

### チケットB-1: pgvector 拡張とスキーマ準備
- 成果物: `embedding halfvec(3072)` カラム、HNSWインデックス（pgvector ≥ 0.7）、検索 RPC
- SQL（Supabase SQL Editor）:
  - 注意: `halfvec`（16-bit 浮動小数）と HNSW の 4000 次元上限は pgvector 0.7 以降で有効です（従来の `vector` + HNSW は 2000 次元上限）。
```sql
-- 1) pgvector を有効化（未導入なら）
create extension if not exists vector;

-- 2) 埋め込みカラムを追加（例: 3072次元：Azure text-embedding-3-large）
alter table public.products
  add column if not exists embedding halfvec(3072);

-- 3) 検索高速化（コサイン類似 / HNSW）
create index if not exists products_embedding_hnsw
on public.products using hnsw (embedding halfvec_cosine_ops);

analyze public.products;

-- 4) 類似検索用 RPC（cosine 類似度）
create or replace function public.match_products (
  query_embedding halfvec(3072),
  match_threshold float,
  match_count int
) returns table (
  id uuid,
  name text,
  description text,
  cost int,
  similarity float
) language sql stable as $$
  select
    p.id, p.name, p.description, p.cost,
    1 - (p.embedding <=> query_embedding) as similarity
  from public.products p
  where p.embedding is not null
    and 1 - (p.embedding <=> query_embedding) >= match_threshold
  order by p.embedding <=> query_embedding
  limit match_count;
$$;
```

（フォールバック）pgvector < 0.7 もしくは 32-bit 精度を維持したい場合は、`vector(3072)` + IVFFlat を利用してください。
```sql
-- 32-bit vector + IVFFlat（cosine）
alter table public.products
  add column if not exists embedding vector(3072);

create index if not exists products_embedding_ivfflat
on public.products using ivfflat (embedding vector_cosine_ops)
with (lists = 100);

analyze public.products;
```

### チケットB-2: 既存データに埋め込みをバックフィル（Azure OpenAI 版）
- 成果物: `products.embedding` にベクトルが格納済み
- 事前: `.env` に以下を設定
  - `SUPABASE_URL=...`
  - `SUPABASE_SERVICE_ROLE_KEY=...`
  - `AZURE_OPENAI_ENDPOINT=...`
  - `AZURE_OPENAI_API_KEY=...`
  - `AZURE_EMBEDDING_DEPLOYMENT=text-embedding-3-large`
- 手順（Python 例・安全に少量ずつ更新）:
```python
import os
from dotenv import load_dotenv
from supabase import create_client
from openai import AzureOpenAI

load_dotenv()
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
client = AzureOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version="2024-05-01-preview",
)
deployment = os.getenv("AZURE_EMBEDDING_DEPLOYMENT", "text-embedding-3-large")

# 1) embedding が未設定の行を取得
rows = supabase.table("products").select("id, description").is_("embedding", None).limit(50).execute().data

for row in rows:
    text = (row.get("description") or "").strip()
    if not text:
        continue
    emb = client.embeddings.create(model=deployment, input=text).data[0].embedding
    supabase.table("products").update({"embedding": emb}).eq("id", row["id"]).execute()
```
※ カラム定義の次元数（例: `halfvec(3072)`）は Azure の実次元（text-embedding-3-large は 3072）に一致させてください。Python 側は通常の `list[float]` を送れば DB 側で `halfvec` に格納されます。

### チケットB-3: Supabase Edge Function で `/retrieval` を実装（Azure OpenAI 版）
- 成果物: Dify 外部ナレッジAPI仕様に準拠したエンドポイント
- 仕様（要点）:
  - Method: `POST <your-endpoint>/retrieval`
  - Header: `Authorization: Bearer {API_KEY}`
  - Body: `{ knowledge_id, query, retrieval_setting: { top_k, score_threshold }, ... }`
  - Response: `{ records: [{ content, score, title, metadata? }, ...] }`
  - 備考: RPC は `query_embedding halfvec(3072)` を受け取る定義です。クライアントからは従来通り数値配列を渡せば問題ありません。
- 最小構成（TypeScript/Edge Functions 概略・Azure Embeddings 呼び出し）:
```ts
// functions/retrieval/index.ts
import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js";
Deno.serve(async (req)=>{
  if (req.method !== "POST") {
    return new Response("Method Not Allowed", {
      status: 405,
      headers: {
        "Content-Type": "text/plain; charset=utf-8"
      }
    });
  }
  const jsonHeaders = {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store"
  };
  // Dify spec: Authorization: Bearer <API_KEY> (here we use anon key)
  const auth = req.headers.get("authorization") || "";
  if (auth !== `Bearer ${Deno.env.get("SUPABASE_ANON_KEY")}`) {
    return Response.json({
      error_code: 1002,
      error_msg: "認証失敗"
    }, {
      status: 401,
      headers: jsonHeaders
    });
  }
  let body;
  try {
    body = await req.json();
  } catch (_) {
    return Response.json({
      error_code: 400,
      error_msg: "Invalid JSON body. Expect knowledge_id, query, retrieval_setting, metadata_condition."
    }, {
      status: 400,
      headers: jsonHeaders
    });
  }
  const { knowledge_id, query, retrieval_setting, metadata_condition } = body ?? {};
  if (typeof knowledge_id !== "string" || typeof query !== "string" || typeof retrieval_setting !== "object" || typeof metadata_condition !== "object") {
    return Response.json({
      error_code: 400,
      error_msg: "Invalid request body. Expect knowledge_id, query, retrieval_setting, metadata_condition."
    }, {
      status: 400,
      headers: jsonHeaders
    });
  }
  const top_k = Number(retrieval_setting?.top_k ?? 5);
  const score_threshold = Number(retrieval_setting?.score_threshold ?? 0.5);
  // 1) Azure OpenAI Embeddings
  const endpoint = Deno.env.get("AZURE_OPENAI_ENDPOINT");
  const apiKey = Deno.env.get("AZURE_OPENAI_API_KEY");
  const embeddingDeployment = Deno.env.get("AZURE_EMBEDDING_DEPLOYMENT"); // e.g., text-embedding-3-large
  const embRes = await fetch(`${endpoint}/openai/deployments/${embeddingDeployment}/embeddings?api-version=2024-05-01-preview`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "api-key": apiKey
    },
    body: JSON.stringify({
      input: query
    })
  });
  if (!embRes.ok) {
    const err = await embRes.text();
    return Response.json({
      error_code: 500,
      error_msg: `Embedding error: ${err}`
    }, {
      status: 500,
      headers: jsonHeaders
    });
  }
  const embJson = await embRes.json();
  const embedding = embJson.data?.[0]?.embedding ?? [];
  // 2) Supabase RPC 呼び出し
  const supabase = createClient(Deno.env.get("SUPABASE_URL"), Deno.env.get("SUPABASE_SERVICE_ROLE_KEY"));
  const rpcCount = Math.max(top_k * 5, top_k);
  const runQuery = async (threshold, count)=>{
    const { data, error } = await supabase.rpc("match_products", {
      query_embedding: embedding,
      match_threshold: threshold,
      match_count: count
    });
    if (error) {
      return {
        rows: [],
        err: error.message
      };
    }
    const rows = (data ?? []).map((row)=>({
        content: row.description ?? "",
        score: row.similarity ?? 0,
        title: row.name ?? "",
        metadata: {
          cost: row.cost,
          id: row.id
        }
      }));
    return {
      rows
    };
  };
  const applyFilter = (recs)=>{
    try {
      const logicalOperator = (metadata_condition?.logical_operator ?? "and").toLowerCase() === "or" ? "or" : "and";
      const conditions = Array.isArray(metadata_condition?.conditions) ? metadata_condition.conditions : [];
      if (!conditions.length) return recs;
      const compare = (rec, cond)=>{
        const names = Array.isArray(cond?.name) ? cond.name : [];
        const op = String(cond?.comparison_operator || "").toLowerCase();
        const val = cond?.value;
        const checks = [];
        for (const n of names){
          const key = String(n).toLowerCase();
          if (key === "title") {
            const s = String(rec.title || "");
            if (op === "contains" && typeof val === "string") checks.push(s.includes(val));
            if (op === "not contains" && typeof val === "string") checks.push(!s.includes(val));
            if (op === "empty") checks.push(s.length === 0);
            if (op === "not empty") checks.push(s.length > 0);
          } else if (key === "content") {
            const s = String(rec.content || "");
            if (op === "contains" && typeof val === "string") checks.push(s.includes(val));
            if (op === "not contains" && typeof val === "string") checks.push(!s.includes(val));
            if (op === "empty") checks.push(s.length === 0);
            if (op === "not empty") checks.push(s.length > 0);
          } else if (key === "cost") {
            const num = Number(rec?.metadata?.cost);
            const v = Number(val);
            if (!Number.isNaN(num) && !Number.isNaN(v)) {
              if (op === ">") checks.push(num > v);
              if (op === ">=") checks.push(num >= v);
              if (op === "<") checks.push(num < v);
              if (op === "<=") checks.push(num <= v);
              if (op === "=" || op === "is") checks.push(num === v);
              if (op === "≠" || op === "is not") checks.push(num !== v);
            }
          }
        }
        return checks.length ? checks.some(Boolean) : true;
      };
      const filtered = recs.filter((rec)=>{
        const results = (metadata_condition?.conditions ?? []).map((c)=>compare(rec, c));
        return logicalOperator === "or" ? results.some(Boolean) : results.every(Boolean);
      });
      return filtered;
    } catch (_) {
      return recs; // フィルタ失敗時はそのまま
    }
  };
  // First attempt
  let { rows, err } = await runQuery(score_threshold, rpcCount);
  if (err) {
    return Response.json({
      error_code: 500,
      error_msg: err
    }, {
      status: 500,
      headers: jsonHeaders
    });
  }
  let records = applyFilter(rows);
  // Fallback: if empty, relax threshold to 0.0 and increase count
  if (records.length === 0 && score_threshold > 0) {
    const retry = await runQuery(0.0, Math.max(rpcCount, top_k * 10));
    if (!("err" in retry) && Array.isArray(retry.rows)) {
      records = applyFilter(retry.rows);
    }
  }
  // top_k で打ち切り
  records = records.slice(0, top_k);
  return Response.json({
    records
  }, {
    status: 200,
    headers: jsonHeaders
  });
});
```

環境変数と依存について（重要）
- 環境変数は Edge Functions では `Deno.env.get("...")` で参照します。事前に B-4 の手順で `supabase secrets set` を実行してください。
  - 必要なシークレット例: `SUPABASE_ANON_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_EMBEDDING_DEPLOYMENT`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`
- パッケージインストールは不要です。Supabase Edge Functions は Deno ランタイムで動作し、`npm:@supabase/supabase-js` のようにコード内で直接インポートします（`package.json` や `npm install` は不要）。

## ローカル/本番テスト
- デプロイ後の関数 URL 例: `https://<PROJECT-REF>.supabase.co/functions/v1/retrieval`
- テスト用リクエスト（curl 例）:
```bash
curl -sS -X POST \
  "https://<PROJECT-REF>.supabase.co/functions/v1/retrieval" \
  -H "Authorization: Bearer <SUPABASE_ANON_KEY>" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{
    "knowledge_id": "test-knowledge",
    "query": "軽量ノートPC",
    "retrieval_setting": { "top_k": 3, "score_threshold": 0.5 },
    "metadata_condition": { "logical_operator": "and", "conditions": [] }
  }'
```

- Windows PowerShell 例（文字化け防止）:
```powershell
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()
chcp 65001 > $null
$BASE = "https://<PROJECT-REF>.supabase.co/functions/v1/retrieval"
$API  = "<SUPABASE_ANON_KEY>"
$body = @{
  knowledge_id = "test-knowledge"
  query = "軽量ノートPC"
  retrieval_setting = @{ top_k = 3; score_threshold = 0.5 }
  metadata_condition = @{ logical_operator = "and"; conditions = @() }
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri $BASE \
  -Headers @{ Authorization = "Bearer $API" } \
  -ContentType "application/json; charset=utf-8" \
  -Body $body
```

期待されるレスポンス例（構造）
```json
{
  "records": [
    {
      "content": "14インチの軽量ノートPCで…",        
      "score": 0.82,
      "title": "UltraBook X",
      "metadata": { "cost": 128000, "id": "d2a9..." }
    },
    {
      "content": "持ち運び向け薄型筐体…",
      "score": 0.77,
      "title": "LiteNote 13",
      "metadata": { "cost": 98000, "id": "7f34..." }
    }
  ]
}
```
備考:
- `records.length` は `top_k` 以下。`score` は類似度（0〜1 目安）。
- 結果が空の場合はしきい値（`score_threshold`）を下げる、または埋め込みバックフィル（B-2）を確認してください。
- フォールバック: 0件だった場合は内部で `score_threshold=0.0` に緩和して再検索し、その上で `top_k` 件に整形して返します。

### リクエスト/レスポンスの項目（意味と形式）
- **エンドポイント**: `POST https://<PROJECT-REF>.supabase.co/functions/v1/retrieval`
- **ヘッダー**:
  - **Authorization**: `Bearer <API_KEY>`（本手順では `SUPABASE_ANON_KEY` を利用）
  - **Content-Type**: `application/json`(`application/json; charset=utf-8`)
- **Request Body**（JSON）:
  - **knowledge_id: string**: 外部ナレッジのコレクション識別子（本ハンズオンでは任意の安定文字列）
  - **query: string**: ユーザーの質問文。埋め込み生成の入力
  - **retrieval_setting: object**
    - **top_k: number**: 返却上限件数（例: 3, 5, 10）
    - **score_threshold: number**: 類似度の下限（0.0〜1.0）。0に近いほど緩い
  - **metadata_condition: object**（任意の簡易フィルタ）
    - **logical_operator: "and" | "or"**: 条件の結合方法（既定: and）
    - **conditions: Array<object>**: 条件配列。各要素の例:
      - **name: string[]**: 対象フィールド名（例: ["title"], ["content"], ["cost"]）
      - **comparison_operator: string**: 比較演算子（contains, not contains, =, ≠, >, >=, <, <=, empty, not empty など）
      - **value: string | number | null**: 比較値（演算子により省略可）
- **Response Body**（JSON 成功時 200）:
  - **records: Array<object>**: 検索結果
    - **title: string**: ドキュメントタイトル等
    - **content: string**: 抜粋テキスト（コンテキスト）
    - **score: number**: 類似度スコア（0〜1目安）
    - **metadata?: object**: 任意メタ（例: `{"cost": 128000, "id": "..."}`）
- **エラー**（JSON）:
  - **error_code: number**（例: 1001 無効ヘッダー形式, 1002 認証失敗, 2001 ナレッジ不存在）
  - **error_msg: string**

### 簡易疑似コード（サーバ: Edge Function）
```ts
serve(req) {
  assertMethodPost(req)
  assertAuthHeader(req, env.SUPABASE_ANON_KEY)

  const { knowledge_id, query, retrieval_setting, metadata_condition } = parseJson(req)
  const topK = retrieval_setting.top_k ?? 5
  const threshold = retrieval_setting.score_threshold ?? 0.5

  // 1) 埋め込み生成（Azure OpenAI）
  const embedding = azureEmbeddings(query, env.AZURE_*)

  // 2) ベクトル検索（RPC）
  const rpcCount = Math.max(topK * 5, topK)
  let rows = rpcMatchProducts(embedding, threshold, rpcCount)

  // 3) 条件フィルタ
  let records = applyMetadataFilter(mapRows(rows), metadata_condition)

  // 4) フォールバック（0件時）
  if (records.length === 0 && threshold > 0) {
    rows = rpcMatchProducts(embedding, 0.0, Math.max(rpcCount, topK * 10))
    records = applyMetadataFilter(mapRows(rows), metadata_condition)
  }

  return json({ records: records.slice(0, topK) }, 200, utf8Headers)
}
```

### 簡易疑似コード（クライアント: Dify からの呼び出し相当）
```ts
const body = {
  knowledge_id: "products",
  query: userInput,
  retrieval_setting: { top_k: 5, score_threshold: 0.5 },
  metadata_condition: { logical_operator: "and", conditions: [] },
}
const res = await fetch("https://<PROJECT-REF>.supabase.co/functions/v1/retrieval", {
  method: "POST",
  headers: {
    Authorization: `Bearer ${ANON_KEY}`,
    "Content-Type": "application/json; charset=utf-8",
  },
  body: JSON.stringify(body),
})
const { records } = await res.json()
// records をプロンプトのコンテキストに整形して利用
```

### チケットB-4: Edge Function のデプロイとシークレット設定（Azure 用）
- 成果物: 公開 URL が発行され `/retrieval` が利用可能
- 手順（ローカルに Supabase CLI がある前提）:
```bash
supabase functions new retrieval
# 上記の index.ts を配置
supabase secrets set \
  SUPABASE_ANON_KEY=your-secret \
  AZURE_OPENAI_ENDPOINT=https://<your-aoai>.openai.azure.com \
  AZURE_OPENAI_API_KEY=xxxx \
  AZURE_EMBEDDING_DEPLOYMENT=text-embedding-3-large \
  SUPABASE_URL=https://<PROJECT-REF>.supabase.co \
  SUPABASE_SERVICE_ROLE_KEY=xxxx
# デプロイ
supabase functions deploy retrieval --no-verify-jwt
```
- verify_jwt について: `Authorization: Bearer <SUPABASE_ANON_KEY>` を利用する運用であれば有効/無効どちらでも動作します。Dify の仕様に合わせるなら `--no-verify-jwt` で問題ありません。

### チケットB-5: Dify に「外部ナレッジAPI」を登録
- 成果物: Dify からテストが green
- 手順:
  1. Dify → ナレッジ → 外部ナレッジAPI → 追加
  2. エンドポイント: `<Edge Function の URL>/retrieval`
  3. API-Key: `SUPABASE_ANON_KEY`
  4. 接続テスト → 成功

### チケットB-6: 外部ナレッジベースを作成しアプリで利用
- 成果物: アプリの回答で意味検索の引用が返る
- 手順:
  1. Dify → ナレッジベースを追加 → 外部ナレッジに接続
  2. knowledge_id: 任意、retrieval_setting: `top_k`, `score_threshold` を設定
  3. 対象アプリのナレッジとして有効化 → チャット/フローで動作確認

---

## MCP（Cursor）での補助（任意）
このリポジトリには、Cursor と Supabase MCP の接続手順があります。設定しておくと、拡張確認や SQL 投入をエディタ内から行えて便利です。

```14:24:docs/supabase-mcp-setup.md
{
  "mcpServers": {
    "supabase": {
      "command": "npx",
      "args": ["-y", "@supabase/mcp-server-supabase@latest"],
      "env": { "SUPABASE_ACCESS_TOKEN": "${SUPABASE_ACCESS_TOKEN}" }
    }
  }
}
```

---

## セキュリティ注意
- Supabase の anon key / service role key / DB パスワードはリポジトリにコミットしない
- Dify 側の API-Key（外部ナレッジAPI 認証）も同様
- Edge Function 側は `SERVICE_ROLE_KEY` を使うため、必ず関数内で Bearer 認証を必須にする

---

## トラブルシューティング（要点）
- 401（認証エラー）: Dify → `/retrieval` の Authorization ヘッダを再確認
- 500: RPC 名やパラメータ不一致、埋め込み未作成、拡張未導入を確認
- 検索が0件: `score_threshold` を下げる / 埋め込み次元・モデルの一致確認

---

## 参考リンク
- 外部ナレッジAPI 仕様（`/retrieval`）: [Dify Docs](https://legacy-docs.dify.ai/ja-jp/guides/knowledge-base/external-knowledge-api-documentation)
- 外部ナレッジベースへの接続ガイド: [Dify Docs（GitHub）](https://github.com/langgenius/dify-docs/blob/main/jp/guides/knowledge-base/connect-external-knowledge-base.md)
- Supabase / pgvector 概要: `vector` 拡張（HNSW/IVFFlat、cosine 距離）公式ドキュメント参照




## Dify の HTTP ツール用カスタム API（2ヘッダー設定＋OpenAPI）

この節では、Dify の「HTTP Request」ノードから Supabase Edge Function（`/retrieval`）を直接呼び出すための設定方法と、OpenAPI 3.1.1 準拠のスキーマ例を示します。OpenAPI の仕様は [OpenAPI 3.1.1](https://swagger.io/specification/) に準拠しています。

### 2つのヘッダー設定（Authorization と apikey）
- 設定場所: Dify → Flow/Workflow → ノード追加 → HTTP Request
- 入力項目:
  - Method: `POST`
  - URL: `https://<PROJECT-REF>.supabase.co/functions/v1/retrieval`
  - Headers:
    - `Authorization`: `Bearer <SUPABASE_ANON_KEY>`
    - `apikey`（任意）: `<SUPABASE_ANON_KEY>`
  - Body: `application/json` を選択し、以下の JSON を貼り付け
```json
{
  "knowledge_id": "products",
  "query": "軽量ノートPC",
  "retrieval_setting": { "top_k": 3, "score_threshold": 0.5 },
  "metadata_condition": { "logical_operator": "and", "conditions": [] }
}
```

備考:
- Edge Function 側の実装例では `Authorization` の Bearer 検証のみで十分です。`apikey` は Supabase REST 直叩きの慣習であり、Edge Function では必須ではありませんが、必要に応じて 2 つ目のヘッダーとして併用できます。
- `Content-Type` は Dify の HTTP Request ノードで Body を JSON に設定すれば自動で `application/json` が付与されます。

### OpenAPI schema（YAML, 3.1.1, apikey ヘッダーを任意で定義）
以下は `/retrieval` エンドポイントの OpenAPI 3.1.1 スキーマ例です。`Authorization` は `securitySchemes`＋`security` で扱い、追加ヘッダー `apikey` は `parameters` の `in: header` として任意指定にしています。

```yaml
openapi: 3.1.1
info:
  title: Dify External Knowledge Retrieval (Supabase Edge Function)
  version: "1.0.0"
  description: REST endpoint implementing Dify External Knowledge API `/retrieval`.

servers:
  - url: https://{projectRef}.supabase.co/functions/v1
    variables:
      projectRef:
        description: Supabase project reference (e.g., abcdefghijklmnopqrst)
        default: your-project-ref

tags:
  - name: Retrieval
    description: External knowledge retrieval via pgvector similarity search.

paths:
  /retrieval:
    post:
      tags: [Retrieval]
      summary: Retrieve semantically similar product records
      operationId: postRetrieval
      security:
        - bearerAuth: []
      parameters:
        - in: header
          name: apikey
          required: false
          schema:
            type: string
          description: Optional second header; often same value as anon key.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/RetrievalRequest"
            examples:
              example:
                summary: Basic request
                value:
                  knowledge_id: "products"
                  query: "軽量ノートPC"
                  retrieval_setting:
                    top_k: 3
                    score_threshold: 0.5
                  metadata_condition:
                    logical_operator: "and"
                    conditions: []
      responses:
        "200":
          description: Successful retrieval
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/RetrievalResponse"
              examples:
                example:
                  summary: Example response
                  value:
                    records:
                      - title: "UltraBook X"
                        content: "14インチの軽量ノートPCで…"
                        score: 0.82
                        metadata:
                          cost: 128000
                          id: "d2a9f1d6-1111-2222-3333-44b3a52e1a1a"
                      - title: "LiteNote 13"
                        content: "持ち運び向け薄型筐体…"
                        score: 0.77
                        metadata:
                          cost: 98000
                          id: "7f34bdb1-1111-2222-3333-99f7a12d55aa"
        "400":
          description: Invalid request body
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ErrorResponse"
        "401":
          description: Authentication failed
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ErrorResponse"
        "500":
          description: Server error (embedding generation, RPC call, etc.)
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ErrorResponse"

components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT

  schemas:
    RetrievalRequest:
      type: object
      description: Request schema for `/retrieval`.
      required:
        - knowledge_id
        - query
        - retrieval_setting
        - metadata_condition
      properties:
        knowledge_id:
          type: string
          description: Identifier of the knowledge collection.
          minLength: 1
        query:
          type: string
          description: User query text used to generate the embedding.
          minLength: 1
        retrieval_setting:
          $ref: "#/components/schemas/RetrievalSetting"
        metadata_condition:
          $ref: "#/components/schemas/MetadataCondition"

    RetrievalSetting:
      type: object
      description: Retrieval parameters.
      properties:
        top_k:
          type: integer
          minimum: 1
          default: 5
          description: Max number of records to return.
        score_threshold:
          type: number
          minimum: 0
          maximum: 1
          default: 0.5
          description: Minimum similarity score (0.0–1.0). Lower is more lenient.

    MetadataCondition:
      type: object
      description: Optional client-side filtering applied after similarity search.
      required:
        - logical_operator
        - conditions
      properties:
        logical_operator:
          type: string
          enum: [and, or]
          default: and
          description: Logical operator to combine conditions.
        conditions:
          type: array
          items:
            $ref: "#/components/schemas/Condition"

    Condition:
      type: object
      description: A single filter condition.
      required:
        - name
        - comparison_operator
      properties:
        name:
          type: array
          description: Target fields; supported examples include "title", "content", "cost".
          items:
            type: string
        comparison_operator:
          type: string
          description: Comparison operator.
          enum:
            - contains
            - not contains
            - ">"
            - ">="
            - "<"
            - "<="
            - "="
            - is
            - "≠"
            - is not
            - empty
            - not empty
        value:
          description: Comparison value; omitted for empty/not empty.
          oneOf:
            - type: string
            - type: number
            - type: "null"

    RetrievalRecord:
      type: object
      description: Retrieval result record.
      properties:
        title:
          type: string
        content:
          type: string
        score:
          type: number
          minimum: 0
          maximum: 1
        metadata:
          type: object
          additionalProperties: true
          properties:
            id:
              type: string
              format: uuid
            cost:
              type: integer
              minimum: 0

    RetrievalResponse:
      type: object
      description: Successful response containing records.
      properties:
        records:
          type: array
          items:
            $ref: "#/components/schemas/RetrievalRecord"
      required:
        - records

    ErrorResponse:
      type: object
      description: Error payload.
      required: [error_code, error_msg]
      properties:
        error_code:
          type: integer
        error_msg:
          type: string
```